"""Forward rollout for what-if and replay. Ts and Pr are empirical, not physics."""

from __future__ import annotations

import numpy as np

from htpp.constants import CP_CHARGE_J_PER_KG_K


def simulate_batch(
    *,
    feed_mass_kg: float,
    moisture_pct: float,
    feedstock_type: str,
    target_peak_tr_c: float,
    heating_power_scale: float,
    amb_temp_c: float,
    ua_w_per_k: float,
    c_shell_j_per_k: float,
    q_h_w: float,
    step_s: float = 60.0,
    train_ranges: dict | None = None,
) -> dict:
    c_eff = c_shell_j_per_k + feed_mass_kg * CP_CHARGE_J_PER_KG_K
    ua = max(ua_w_per_k, 1.0)
    tau = c_eff / ua
    q_in = q_h_w * heating_power_scale
    tr = amb_temp_c + 2.0
    t = 0.0
    rows_t, rows_tr, rows_state = [], [], []
    phase = "heating"
    # Cap at 30 h so a bad parameter set cannot spin forever.
    while t < 30 * 3600:
        rows_t.append(t)
        rows_tr.append(tr)
        rows_state.append(phase)
        if phase == "heating" and tr >= target_peak_tr_c:
            phase = "gas"
        elif phase == "gas" and t > rows_t[0] + 6 * 3600 and tr >= target_peak_tr_c - 5:
            # Gas duration scales gently with moisture; this is a regression stand-in.
            if t > 6.5 * 3600 + moisture_pct * 120:
                phase = "cooling"
                q_in = 0.0
        elif phase == "cooling" and tr < amb_temp_c + 40:
            phase = "n2_purging"
        elif phase == "n2_purging" and tr < amb_temp_c + 25:
            phase = "carbon_discharge"
        elif phase == "carbon_discharge" and t - rows_t[rows_state.index("carbon_discharge")] > 2.5 * 3600:
            phase = "main_door_open"
        elif phase == "main_door_open" and len(rows_state) > 5 and rows_state[-5] == "main_door_open":
            break
        dtr = (q_in - ua * (tr - amb_temp_c)) / c_eff
        tr = float(np.clip(tr + dtr * step_s, 0.0, 900.0))
        t += step_s
        if phase == "main_door_open" and rows_state[-1] == "main_door_open" and t > rows_t[-1]:
            if rows_state.count("main_door_open") > int(3600 / step_s):
                break

    phases = _collapse(rows_t, rows_state)
    oil = 38.0 + 0.04 * (target_peak_tr_c - 400) - 0.3 * moisture_pct
    carbon = 32.0 - 0.02 * (target_peak_tr_c - 400)
    steel = 15.0 if "mix" in feedstock_type else 12.0
    warnings = _warnings(feed_mass_kg, moisture_pct, target_peak_tr_c, train_ranges or {})
    return {
        "t_offset_s": [int(v) for v in rows_t[:: max(1, int(60 / step_s))]],
        "tr_c": [round(v, 1) for v in rows_tr[:: max(1, int(60 / step_s))]],
        "process_state": rows_state[:: max(1, int(60 / step_s))],
        "phases": phases,
        "predicted_total_duration_min": round(rows_t[-1] / 60.0, 1),
        "predicted_yields": {
            "oil_yield_pct": {"p10": round(oil - 3, 1), "p50": round(oil, 1), "p90": round(oil + 3, 1)},
            "carbon_yield_pct": {"p10": round(carbon - 2, 1), "p50": round(carbon, 1), "p90": round(carbon + 2, 1)},
            "steel_yield_pct": {"p10": round(steel - 1, 1), "p50": round(steel, 1), "p90": round(steel + 1, 1)},
        },
        "extrapolation_warnings": warnings,
        "empirical_note": "Ts and Pr are not simulated from first principles.",
    }


def _collapse(times: list[float], states: list[str]) -> list[dict]:
    if not states:
        return []
    out = []
    start = 0
    for i in range(1, len(states) + 1):
        if i == len(states) or states[i] != states[start]:
            out.append({
                "process_state": states[start],
                "start_s": times[start],
                "end_s": times[i - 1],
                "duration_min": (times[i - 1] - times[start]) / 60.0,
            })
            start = i
    return out


def _warnings(feed: float, moisture: float, peak: float, ranges: dict) -> list[str]:
    labels = {
        "feed_mass_kg": ("Feed charge", "kg", 0),
        "moisture_pct": ("Moisture", "%", 1),
        "target_peak_tr_c": ("Target peak temperature", "°C", 0),
    }
    warnings = []
    for name, value in (("feed_mass_kg", feed), ("moisture_pct", moisture), ("target_peak_tr_c", peak)):
        bounds = ranges.get(name)
        if not bounds:
            continue
        lo, hi = bounds
        if value < lo or value > hi:
            label, unit, digits = labels[name]
            warnings.append(
                f"{label} {value:.{digits}f} {unit} is outside what this plant has logged "
                f"({lo:.{digits}f}–{hi:.{digits}f} {unit}). Treat the projection as a rough guide only."
            )
    return warnings
