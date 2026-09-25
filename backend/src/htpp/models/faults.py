"""Residual detectors. Matching window is 120 minutes, fixed before results."""

from __future__ import annotations

import numpy as np
import pandas as pd

from htpp.constants import FAULT_MATCH_WINDOW_MIN

LAM = 0.3
K_CUSUM = 0.5


def run_detectors(residual: np.ndarray, h_ewma: float = 3.0, h_cusum: float = 4.0) -> dict[str, np.ndarray]:
    z = np.zeros_like(residual)
    sp = np.zeros_like(residual)
    sm = np.zeros_like(residual)
    for i, value in enumerate(residual):
        prev_z = 0.0 if i == 0 else z[i - 1]
        z[i] = LAM * value + (1 - LAM) * prev_z
        prev_p = 0.0 if i == 0 else sp[i - 1]
        prev_m = 0.0 if i == 0 else sm[i - 1]
        sp[i] = max(0.0, prev_p + value - K_CUSUM)
        sm[i] = max(0.0, prev_m - value - K_CUSUM)
    cusum = np.maximum(sp, sm)
    return {
        "ewma_z": z,
        "cusum": cusum,
        "ewma_alarm": np.abs(z) > h_ewma,
        "cusum_alarm": cusum > h_cusum,
    }


def lead_times(panel_times_min: np.ndarray, detector_times_min: np.ndarray) -> dict:
    """Positive lead time means the detector fired first. Window is 120 min."""
    leads = []
    matched_panel = 0
    for panel_t in panel_times_min:
        earlier = detector_times_min[(detector_times_min <= panel_t) & (panel_t - detector_times_min <= FAULT_MATCH_WINDOW_MIN)]
        if len(earlier):
            leads.append(float(panel_t - earlier.max()))
            matched_panel += 1
    false_pos = 0
    for det_t in detector_times_min:
        window = panel_times_min[(panel_times_min >= det_t) & (panel_times_min - det_t <= FAULT_MATCH_WINDOW_MIN)]
        if len(window) == 0:
            false_pos += 1
    misses = int(len(panel_times_min) - matched_panel)
    arr = np.array(leads) if leads else np.array([])
    return {
        "n_panel_alarms": int(len(panel_times_min)),
        "n_detector_alarms": int(len(detector_times_min)),
        "n_matched": matched_panel,
        "misses": misses,
        "false_positives": false_pos,
        "median_lead_min": None if len(arr) == 0 else float(np.median(arr)),
        "iqr_lead_min": None if len(arr) < 2 else float(np.subtract(*np.percentile(arr, [75, 25]))),
        "matching_window_min": FAULT_MATCH_WINDOW_MIN,
        "resolution_floor_min": 4,
        "leads_min": [round(v, 0) for v in leads],
    }


def batch_residual_frame(samples: pd.DataFrame, predicted_tr: np.ndarray) -> pd.DataFrame:
    measured = pd.to_numeric(samples["tr_c"], errors="coerce").to_numpy()
    resid = measured - predicted_tr
    scale = float(np.nanstd(resid)) or 1.0
    norm = resid / scale
    det = run_detectors(np.nan_to_num(norm))
    return pd.DataFrame({
        "sampled_at": samples["sampled_at"].to_numpy(),
        "r_t_c": resid,
        "r_t_norm": norm,
        "ewma_z": det["ewma_z"],
        "cusum": det["cusum"],
        "alarm": det["cusum_alarm"] | det["ewma_alarm"],
    })
