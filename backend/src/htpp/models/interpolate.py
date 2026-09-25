"""One-second model trajectories for the scene. A diverging solve falls back."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

TR_MIN = 0.0
TR_MAX = 900.0
MAX_ROH = 8.0


@dataclass
class DenseTrajectory:
    step_s: float
    horizon_s: float
    tr_c: list[float]
    ts_c: list[float]
    pr_bar: list[float]
    ps_bar: list[float]
    process_state: list[str]
    interpolation_mode: str


def dense_trajectory(
    *,
    tr_c: float,
    ts_c: float | None,
    pr_bar: float | None,
    ps_bar: float | None,
    amb_temp_c: float | None,
    process_state: str,
    tau_cool_min: float | None,
    q_in_w: float | None,
    ua_w_per_k: float | None,
    horizon_s: float = 300.0,
    step_s: float = 1.0,
) -> DenseTrajectory:
    n = int(horizon_s / step_s) + 1
    if not np.isfinite(tr_c):
        tr_c = 30.0
    amb = 28.0 if amb_temp_c is None or not np.isfinite(amb_temp_c) else amb_temp_c
    ts0 = tr_c if ts_c is None or not np.isfinite(ts_c) else ts_c
    pr0 = 0.0 if pr_bar is None or not np.isfinite(pr_bar) else pr_bar
    ps0 = 0.0 if ps_bar is None or not np.isfinite(ps_bar) else ps_bar
    mode = "model"
    if not tau_cool_min or not ua_w_per_k or tau_cool_min <= 0 or ua_w_per_k <= 0:
        mode = "linear_fallback"
        tr = [round(float(tr_c), 1)] * n
        return _pack(step_s, horizon_s, tr, [round(ts0, 1)] * n, [round(pr0, 3)] * n, [round(ps0, 3)] * n, [process_state] * n, mode)

    tau_s = tau_cool_min * 60.0
    q_in = 0.0 if process_state in {"cooling", "n2_purging", "carbon_discharge", "main_door_open", "idle"} else (q_in_w or 0.0)
    tr_vals = []
    ts_vals = []
    pr_vals = []
    current = float(tr_c)
    current_ts = float(ts0)
    diverged = False
    for i in range(n):
        tr_vals.append(current)
        ts_vals.append(current_ts)
        pr_vals.append(pr0 if process_state != "gas" else pr0 + 0.02 * (1 - np.exp(-i / 80.0)))
        dtr = (q_in - ua_w_per_k * (current - amb)) / max(ua_w_per_k * tau_s, 1.0)
        roh = dtr * 60.0
        if abs(roh) > MAX_ROH * 3 or not np.isfinite(current):
            diverged = True
            break
        current = float(np.clip(current + dtr * step_s, TR_MIN, TR_MAX))
        current_ts = float(current_ts + ((current - current_ts) / 600.0) * step_s)
    if diverged or len(tr_vals) != n:
        mode = "linear_fallback"
        tr_vals = [round(float(tr_c), 1)] * n
        ts_vals = [round(ts0, 1)] * n
        pr_vals = [round(pr0, 3)] * n
    return _pack(
        step_s,
        horizon_s,
        [round(v, 1) for v in tr_vals],
        [round(v, 1) for v in ts_vals],
        [round(float(v), 3) for v in pr_vals],
        [round(ps0, 3)] * n,
        [process_state] * n,
        mode,
    )


def _pack(step_s, horizon_s, tr, ts, pr, ps, states, mode) -> DenseTrajectory:
    return DenseTrajectory(step_s, horizon_s, tr, ts, pr, ps, states, mode)
