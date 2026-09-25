"""Quality flags. had_fault never excludes a batch from training."""

from __future__ import annotations

import numpy as np
import pandas as pd

EXCLUDING = {
    "incomplete_batch",
    "ingestion_gap",
    "sparse_sampling",
    "too_few_samples",
    "mass_balance_impossible",
    "batch_no_reset",
}


def usable_for_training(flags: list[str]) -> bool:
    return not any(flag in EXCLUDING for flag in flags)


def quality_flags(
    *,
    group: pd.DataFrame,
    phase_names: list[str],
    deltas_s: np.ndarray,
    previous_batch_no: int | None,
    batch_no: int,
    has_excel: bool,
) -> list[str]:
    flags: list[str] = []
    has_heating = "heating" in phase_names
    has_terminal = "main_door_open" in phase_names or "idle" in phase_names
    if not has_heating or not has_terminal:
        flags.append("incomplete_batch")
    if len(deltas_s) and float(np.max(deltas_s)) > 1800:
        flags.append("ingestion_gap")
    if len(deltas_s) and float(np.median(deltas_s)) > 600:
        flags.append("sparse_sampling")
    if len(group) < 60:
        flags.append("too_few_samples")
    if not has_excel:
        flags.append("no_excel_log")
    faults = set(group["fault_state"].astype(str)) - {"none", "nan", "None"}
    if faults:
        flags.append("had_fault")
    if (group["pr_bar"].isna() & group["process_raw"].astype(str).str.upper().eq("OPEN")).any():
        flags.append("pr_non_numeric")
    if (group["process_state"].astype(str) == "unknown").any():
        flags.append("unknown_process_state")
    versions = group["panel_version"].dropna().astype(str)
    counts = versions.value_counts()
    # A single stray reading of a neighbouring firmware string is flicker, not a
    # rollout. 426.2 vs 427.2 (and 526.2 vs 527.2) is a handful of samples.
    if len(counts) > 1:
        minority = int(counts.iloc[1])
        if minority >= 5 and minority / int(counts.sum()) >= 0.05:
            flags.append("panel_version_changed")
    if previous_batch_no is not None and batch_no < previous_batch_no:
        flags.append("batch_no_reset")
    if _phase_order_anomaly(phase_names):
        flags.append("phase_order_anomaly")
    return flags


_EXPECTED = ["heating", "gas", "cooling", "n2_purging", "carbon_discharge", "main_door_open"]


def _phase_order_anomaly(names: list[str]) -> bool:
    filtered = [name for name in names if name not in {"idle", "solenoid_on", "unknown"}]
    positions = []
    for name in filtered:
        if name in _EXPECTED:
            positions.append(_EXPECTED.index(name))
    return any(b < a for a, b in zip(positions, positions[1:]))
