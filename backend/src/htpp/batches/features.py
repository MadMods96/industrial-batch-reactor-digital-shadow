"""Thermal severity features. Integrals use real elapsed time, never a fixed dt."""

from __future__ import annotations

import numpy as np
import pandas as pd

from htpp.batches.quality import usable_for_training

T_REF_C = 350.0


def time_above(times_s: np.ndarray, values: np.ndarray, threshold: float) -> float:
    """Trapezoid minutes spent above a temperature threshold."""
    if len(values) < 2:
        return 0.0
    total = 0.0
    for i in range(len(values) - 1):
        dt_min = (times_s[i + 1] - times_s[i]) / 60.0
        a = values[i] - threshold
        b = values[i + 1] - threshold
        if a <= 0 and b <= 0:
            continue
        if a >= 0 and b >= 0:
            total += dt_min
            continue
        frac = abs(a) / (abs(a) + abs(b))
        total += dt_min * (1 - frac if a < 0 else frac)
    return float(total)


def severity_index(times_s: np.ndarray, values: np.ndarray, t_ref: float = T_REF_C) -> float:
    """∫ max(0, Tr - T_ref) dt in degC·min, trapezoid on real timestamps."""
    if len(values) < 2:
        return 0.0
    excess = np.maximum(0.0, values - t_ref)
    total = 0.0
    for i in range(len(values) - 1):
        dt_min = (times_s[i + 1] - times_s[i]) / 60.0
        total += 0.5 * (excess[i] + excess[i + 1]) * dt_min
    return float(total)


def build_features(
    telemetry: pd.DataFrame,
    batches: pd.DataFrame,
    phases: pd.DataFrame,
    yields: pd.DataFrame,
    logs: pd.DataFrame,
) -> pd.DataFrame:
    rows = []
    if batches.empty:
        return pd.DataFrame()
    telemetry = telemetry.copy()
    telemetry["sampled_at"] = pd.to_datetime(telemetry["sampled_at"], utc=True)
    yield_ix = {}
    if not yields.empty:
        for rec in yields.to_dict("records"):
            yield_ix[(int(rec["machine_id"]), int(rec["batch_no"]))] = rec
    log_ix = {}
    if not logs.empty:
        for rec in logs.to_dict("records"):
            log_ix[(int(rec["machine_id"]), int(rec["batch_no"]))] = rec

    for batch in batches.to_dict("records"):
        key = batch["batch_key"]
        samples = telemetry[
            (telemetry["machine_id"] == batch["machine_id"])
            & (telemetry["batch_no"] == batch["batch_no"])
        ].sort_values("sampled_at")
        phase_rows = phases[phases["batch_key"] == key] if not phases.empty else pd.DataFrame()
        times = samples["sampled_at"].map(lambda t: t.timestamp()).to_numpy()
        tr = pd.to_numeric(samples["tr_c"], errors="coerce").to_numpy()
        mask = ~np.isnan(tr)
        times_v, tr_v = times[mask], tr[mask]
        pr = pd.to_numeric(samples["pr_bar"], errors="coerce")
        gas = phase_rows[phase_rows["process_state"] == "gas"] if not phase_rows.empty else pd.DataFrame()
        heating = phase_rows[phase_rows["process_state"] == "heating"] if not phase_rows.empty else pd.DataFrame()
        y = yield_ix.get((int(batch["machine_id"]), int(batch["batch_no"])), {})
        log_row = log_ix.get((int(batch["machine_id"]), int(batch["batch_no"])), {})
        flags = list(batch.get("quality_flags") or [])
        rows.append({
            "batch_key": key,
            "machine_id": int(batch["machine_id"]),
            "started_at": batch["started_at"],
            "heating_duration_min": _sum_duration(phase_rows, "heating"),
            "gas_duration_min": _sum_duration(phase_rows, "gas"),
            "cooling_duration_min": _sum_duration(phase_rows, "cooling"),
            "n2_purge_duration_min": _sum_duration(phase_rows, "n2_purging"),
            "carbon_discharge_duration_min": _sum_duration(phase_rows, "carbon_discharge"),
            "total_duration_min": batch["total_duration_min"],
            "peak_tr_c": batch["peak_tr_c"],
            "mean_roh_heating_c_per_min": _mean(heating, "mean_roh_c_per_min"),
            "max_roh_c_per_min": _nanmax(samples["roh_c_per_min"]),
            "time_above_350c_min": time_above(times_v, tr_v, 350),
            "time_above_400c_min": time_above(times_v, tr_v, 400),
            "time_above_450c_min": time_above(times_v, tr_v, 450),
            "severity_index_c_min": severity_index(times_v, tr_v),
            "tau_cool_min": None,
            "ua_eff_w_per_k": None,
            "c_eff_j_per_k": None,
            "q_in_heating_w": None,
            "alpha_final": None,
            "e_rxn_j": None,
            "max_pr_bar": batch["peak_pr_bar"],
            "mean_pr_gas_bar": _gas_mean_pr(samples, gas),
            "pr_oscillation_count": _oscillations(pr.to_numpy()),
            "pr_integral_bar_min": _integral(times, pr.to_numpy()),
            "mean_amb_temp_c": _nanmean(samples["amb_temp_c"]),
            "feed_mass_kg": log_row.get("feed_mass_kg"),
            "moisture_pct": log_row.get("moisture_pct"),
            "feedstock_type": log_row.get("feedstock_type"),
            "oil_yield_pct": y.get("oil_yield_pct"),
            "carbon_yield_pct": y.get("carbon_yield_pct"),
            "steel_yield_pct": y.get("steel_yield_pct"),
            "closure_error_pct": y.get("closure_error_pct"),
            "had_fault": bool(batch["had_fault"]),
            "quality_flags": flags,
            "usable_for_training": usable_for_training(flags),
        })
    return pd.DataFrame(rows)


def compute_yields(logs: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for rec in logs.to_dict("records"):
        feed = rec["feed_mass_kg"]
        if not feed:
            continue
        oil = 100.0 * rec["oil_mass_kg"] / feed
        carbon = 100.0 * rec["carbon_mass_kg"] / feed
        steel = 100.0 * rec["steel_mass_kg"] / feed
        gas = None if rec.get("gas_mass_kg") is None or pd.isna(rec.get("gas_mass_kg")) else 100.0 * rec["gas_mass_kg"] / feed
        accounted = oil + carbon + steel + (gas or 0.0)
        dry = feed * (1 - rec["moisture_pct"] / 100.0)
        rows.append({
            "machine_id": int(rec["machine_id"]),
            "batch_no": int(rec["batch_no"]),
            "oil_yield_pct": oil,
            "carbon_yield_pct": carbon,
            "steel_yield_pct": steel,
            "gas_yield_pct": gas,
            "accounted_pct": accounted,
            "closure_error_pct": 100.0 - accounted,
            "dry_feed_mass_kg": dry,
            "oil_yield_dry_pct": 100.0 * rec["oil_mass_kg"] / dry if dry else None,
        })
    return pd.DataFrame(rows)


def _sum_duration(phases: pd.DataFrame, state: str) -> float:
    if phases.empty:
        return 0.0
    subset = phases[phases["process_state"] == state]
    if subset.empty:
        return 0.0
    return float(subset["duration_min"].sum())


def _mean(frame: pd.DataFrame, column: str) -> float | None:
    if frame.empty or column not in frame:
        return None
    values = pd.to_numeric(frame[column], errors="coerce").dropna()
    return float(values.mean()) if not values.empty else None


def _nanmax(series: pd.Series) -> float | None:
    values = pd.to_numeric(series, errors="coerce").dropna()
    return float(values.max()) if not values.empty else None


def _nanmean(series: pd.Series) -> float | None:
    values = pd.to_numeric(series, errors="coerce").dropna()
    return float(values.mean()) if not values.empty else None


def _gas_mean_pr(samples: pd.DataFrame, gas: pd.DataFrame) -> float | None:
    if gas.empty:
        return None
    start = pd.Timestamp(gas["started_at"].iloc[0])
    end = pd.Timestamp(gas["ended_at"].iloc[-1])
    window = samples[(samples["sampled_at"] >= start) & (samples["sampled_at"] <= end)]
    return _nanmean(window["pr_bar"])


def _oscillations(pr: np.ndarray) -> int:
    values = pr[~np.isnan(pr)]
    if len(values) < 3:
        return 0
    delta = np.diff(values)
    signs = np.sign(delta)
    signs = signs[signs != 0]
    if len(signs) < 2:
        return 0
    return int(np.sum(signs[1:] * signs[:-1] < 0))


def _integral(times: np.ndarray, values: np.ndarray) -> float | None:
    mask = ~np.isnan(values)
    if mask.sum() < 2:
        return None
    t, v = times[mask], values[mask]
    total = 0.0
    for i in range(len(v) - 1):
        total += 0.5 * (v[i] + v[i + 1]) * (t[i + 1] - t[i]) / 60.0
    return float(total)
