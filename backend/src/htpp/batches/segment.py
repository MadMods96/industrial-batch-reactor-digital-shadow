"""Telemetry to batches and contiguous process phases."""

from __future__ import annotations

from datetime import datetime

import numpy as np
import pandas as pd

from htpp.batches.quality import quality_flags, usable_for_training


def segment(telemetry: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    if telemetry.empty:
        return pd.DataFrame(), pd.DataFrame()
    frame = telemetry.sort_values(["machine_id", "sampled_at"]).copy()
    frame["process_state"] = frame["process_state"].map(lambda value: getattr(value, "value", value)).astype(str)
    frame["fault_state"] = frame["fault_state"].map(lambda value: getattr(value, "value", value)).astype(str)
    frame["sampled_at"] = pd.to_datetime(frame["sampled_at"], utc=True)
    batches: list[dict] = []
    phases: list[dict] = []
    previous_batch_no: dict[int, int] = {}

    for (machine_id, batch_no), group in frame.groupby(["machine_id", "batch_no"], sort=False):
        group = group.sort_values("sampled_at")
        if pd.isna(batch_no):
            continue
        batch_no = int(batch_no)
        machine_id = int(machine_id)
        key = f"{machine_id}-{batch_no}"
        times = group["sampled_at"].tolist()
        deltas = np.diff([t.timestamp() for t in times]) if len(times) > 1 else np.array([])
        states = group["process_state"].astype(str).tolist()
        faults = sorted({f for f in group["fault_state"].astype(str) if f and f != "none"})
        phase_rows = _phases(key, group)
        phases.extend(phase_rows)
        phase_names = [row["process_state"] for row in phase_rows]
        has_heating = "heating" in phase_names
        has_terminal = "main_door_open" in phase_names or "idle" in phase_names
        flags = quality_flags(
            group=group,
            phase_names=phase_names,
            deltas_s=deltas,
            previous_batch_no=previous_batch_no.get(machine_id),
            batch_no=batch_no,
            has_excel=False,
        )
        previous_batch_no[machine_id] = batch_no
        versions = group["panel_version"].dropna().astype(str)
        modal_version = versions.mode().iloc[0] if not versions.empty else None
        batches.append({
            "batch_key": key,
            "machine_id": machine_id,
            "batch_no": batch_no,
            "started_at": times[0],
            "ended_at": times[-1],
            "total_duration_min": (times[-1] - times[0]).total_seconds() / 60.0,
            "n_samples": int(len(group)),
            "median_interval_s": float(np.median(deltas)) if len(deltas) else None,
            "max_gap_s": float(np.max(deltas)) if len(deltas) else 0.0,
            "peak_tr_c": _nanmax(group["tr_c"]),
            "peak_ts_c": _nanmax(group["ts_c"]),
            "peak_pr_bar": _nanmax(group["pr_bar"]),
            "min_pr_bar": _nanmin(group["pr_bar"]),
            "is_complete": bool(has_heating and has_terminal),
            "had_fault": bool(faults),
            "fault_states": faults,
            "panel_version": modal_version,
            "quality_flags": flags,
        })
    batch_frame = pd.DataFrame(batches)
    phase_frame = pd.DataFrame(phases)
    return batch_frame, phase_frame


def apply_excel_flags(batches: pd.DataFrame, logged_keys: set[tuple[int, int]], yields: pd.DataFrame) -> pd.DataFrame:
    if batches.empty:
        return batches
    out = batches.copy()
    closure = {}
    gas_present = {}
    if not yields.empty:
        for row in yields.itertuples(index=False):
            closure[(int(row.machine_id), int(row.batch_no))] = row.closure_error_pct
            gas_present[(int(row.machine_id), int(row.batch_no))] = row.gas_yield_pct is not None and not pd.isna(row.gas_yield_pct)
    flags_out = []
    usable = []
    for row in out.itertuples(index=False):
        flags = list(row.quality_flags or [])
        key = (int(row.machine_id), int(row.batch_no))
        if key in logged_keys:
            flags = [flag for flag in flags if flag != "no_excel_log"]
        elif "no_excel_log" not in flags:
            flags.append("no_excel_log")
        err = closure.get(key)
        if err is not None and not pd.isna(err):
            if err < 0 and "mass_balance_impossible" not in flags:
                flags.append("mass_balance_impossible")
            elif gas_present.get(key) and abs(err) > 5 and "mass_balance_open" not in flags:
                flags.append("mass_balance_open")
        flags_out.append(flags)
        usable.append(usable_for_training(flags))
    out["quality_flags"] = flags_out
    out["usable_for_training"] = usable
    return out


def _phases(batch_key: str, group: pd.DataFrame) -> list[dict]:
    rows: list[dict] = []
    records = group.to_dict("records")
    if not records:
        return rows
    start = 0
    index = 0
    for i in range(1, len(records) + 1):
        boundary = i == len(records) or records[i]["process_state"] != records[start]["process_state"]
        if not boundary:
            continue
        chunk = records[start:i]
        started = _as_dt(chunk[0]["sampled_at"])
        if i < len(records):
            ended = _as_dt(records[i]["sampled_at"])
        else:
            ended = _as_dt(chunk[-1]["sampled_at"])
        tr = [c["tr_c"] for c in chunk if c["tr_c"] is not None and not pd.isna(c["tr_c"])]
        amb = [c["amb_temp_c"] for c in chunk if c["amb_temp_c"] is not None and not pd.isna(c["amb_temp_c"])]
        roh = [c["roh_c_per_min"] for c in chunk if c["roh_c_per_min"] is not None and not pd.isna(c["roh_c_per_min"])]
        rows.append({
            "batch_key": batch_key,
            "phase_index": index,
            "process_state": str(chunk[0]["process_state"]),
            "started_at": started,
            "ended_at": ended,
            "duration_min": (ended - started).total_seconds() / 60.0,
            "n_samples": len(chunk),
            "tr_start_c": tr[0] if tr else None,
            "tr_end_c": tr[-1] if tr else None,
            "tr_peak_c": max(tr) if tr else None,
            "mean_amb_temp_c": float(np.mean(amb)) if amb else None,
            "mean_roh_c_per_min": float(np.mean(roh)) if roh else None,
        })
        index += 1
        start = i
    return rows


def _as_dt(value: object) -> datetime:
    stamp = pd.Timestamp(value)
    if stamp.tzinfo is None:
        stamp = stamp.tz_localize("UTC")
    return stamp.to_pydatetime()


def _nanmax(series: pd.Series) -> float | None:
    values = pd.to_numeric(series, errors="coerce").dropna()
    return float(values.max()) if not values.empty else None


def _nanmin(series: pd.Series) -> float | None:
    values = pd.to_numeric(series, errors="coerce").dropna()
    return float(values.min()) if not values.empty else None
