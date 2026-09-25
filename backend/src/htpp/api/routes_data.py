"""Data, batch and coverage routes."""

from __future__ import annotations

import math
from datetime import datetime, timezone

import pandas as pd
from fastapi import APIRouter, HTTPException, Query, UploadFile

from htpp.batches.assemble import assemble
from htpp.config import ROOT
from htpp.plant import machine_label
from htpp.ingest.excel_log import ExcelMapError, parse_workbook, resolve_batch_numbers
from htpp.models.registry import load_latest
from htpp.store.db import connect, migrate
from htpp.store.queries import (
    batch_counts,
    consecutive_failures,
    daily_coverage,
    gaps,
    ingest_failures,
    last_ingest,
    load_batches,
    load_features,
    load_phases,
    load_telemetry,
    machine_intervals,
    machine_summaries,
    unmapped_values,
)
from htpp.store.writes import upsert_batch_log

router = APIRouter()

SLOTS = {mid: idx for idx, mid in enumerate([1093, 1094, 1146])}


def _con():
    return migrate(connect())


@router.get("/health")
def health() -> dict:
    try:
        con = _con()
        ok = True
        last = last_ingest(con)
        fails = consecutive_failures(con)
        con.close()
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "db_reachable": False, "panel_reachable": None,
                "last_ingest_at": None, "last_ingest_status": str(exc),
                "consecutive_ingest_failures": 0, "model_version": None,
                "interpolation_mode": "linear_fallback"}
    model = load_latest()
    return {
        "status": "ok" if ok else "error",
        "db_reachable": True,
        "panel_reachable": None,
        "last_ingest_at": None if not last else _iso(last[0]),
        "last_ingest_status": None if not last else last[1],
        "consecutive_ingest_failures": fails,
        "model_version": model.get("model_version"),
        "interpolation_mode": model.get("interpolation_mode", "linear_fallback"),
    }


@router.get("/machines")
def machines() -> list[dict]:
    con = _con()
    summary = machine_summaries(con)
    counts = batch_counts(con)
    con.close()
    model = load_latest()
    count_ix = {int(r.machine_id): r for r in counts.itertuples(index=False)} if not counts.empty else {}
    out = []
    seen = set(summary["machine_id"].tolist()) if not summary.empty else set()
    for machine_id in sorted(seen | set(SLOTS)):
        row = summary[summary["machine_id"] == machine_id]
        counted = count_ix.get(int(machine_id))
        out.append({
            "machine_id": int(machine_id),
            "display_name": machine_label(int(machine_id)),
            "panel_chip_id": None if row.empty else _none(row.iloc[0]["panel_chip_id"]),
            "panel_version": None if row.empty else _none(row.iloc[0]["panel_version"]),
            "history_floor": None if row.empty else _iso(row.iloc[0]["history_floor"]),
            "last_sample_at": None if row.empty else _iso(row.iloc[0]["last_sample_at"]),
            "n_samples": 0 if row.empty else int(row.iloc[0]["n_samples"]),
            "n_batches": 0 if counted is None else int(counted.n_batches),
            "n_batches_complete": 0 if counted is None else int(counted.n_batches_complete or 0),
            "has_fitted_model": bool(model.get("per_machine", {}).get(str(int(machine_id)))),
            "scene_slot": SLOTS.get(int(machine_id), 0),
        })
    return out


@router.get("/machines/{machine_id}/telemetry")
def telemetry(machine_id: int, start: str | None = Query(None, alias="from"), to: str | None = None, downsample: int | None = None) -> dict:
    con = _con()
    frame = load_telemetry(con, machine_id, _parse(start), _parse(to))
    con.close()
    samples = [_sample(row) for row in frame.to_dict("records")]
    down = False
    if downsample and len(samples) > downsample:
        samples = _lttb(samples, downsample)
        down = True
    return {
        "machine_id": machine_id,
        "from": start,
        "to": to,
        "n_points": len(samples),
        "downsampled": down,
        "samples": samples,
    }


@router.get("/batches")
def batches(machine_id: int | None = None, had_fault: bool | None = None, usable_only: bool = False, limit: int = 50, offset: int = 0) -> dict:
    con = _con()
    frame = load_batches(con)
    features = load_features(con)
    con.close()
    if frame.empty:
        return {"total": 0, "limit": limit, "offset": offset, "batches": []}
    if machine_id:
        frame = frame[frame["machine_id"] == machine_id]
    if had_fault is not None:
        frame = frame[frame["had_fault"] == had_fault]
    feat = features.set_index("batch_key") if not features.empty else pd.DataFrame()
    rows = []
    for rec in frame.to_dict("records"):
        extra = feat.loc[rec["batch_key"]].to_dict() if rec["batch_key"] in getattr(feat, "index", []) else {}
        if usable_only and not extra.get("usable_for_training"):
            continue
        rows.append({
            "batch_key": rec["batch_key"],
            "machine_id": int(rec["machine_id"]),
            "batch_no": int(rec["batch_no"]),
            "started_at": _iso(rec["started_at"]),
            "ended_at": _iso(rec["ended_at"]),
            "total_duration_min": rec["total_duration_min"],
            "peak_tr_c": rec["peak_tr_c"],
            "is_complete": bool(rec["is_complete"]),
            "had_fault": bool(rec["had_fault"]),
            "fault_states": _as_list(rec["fault_states"]),
            "has_excel_log": "no_excel_log" not in _as_list(rec["quality_flags"]),
            "oil_yield_pct": _none(extra.get("oil_yield_pct")),
            "carbon_yield_pct": _none(extra.get("carbon_yield_pct")),
            "steel_yield_pct": _none(extra.get("steel_yield_pct")),
            "closure_error_pct": _none(extra.get("closure_error_pct")),
            "usable_for_training": bool(extra.get("usable_for_training")),
            "quality_flags": _as_list(rec["quality_flags"]),
        })
    return {"total": len(rows), "limit": limit, "offset": offset, "batches": rows[offset:offset + limit]}


@router.get("/batches/{batch_key}")
def batch_detail(batch_key: str) -> dict:
    con = _con()
    batches = load_batches(con)
    phases = load_phases(con, batch_key)
    features = load_features(con)
    machine_id, batch_no = batch_key.split("-")
    samples = load_telemetry(con, int(machine_id))
    con.close()
    match = batches[batches["batch_key"] == batch_key]
    if match.empty:
        raise HTTPException(status_code=404, detail={"error": {"code": "not_found", "message": batch_key, "detail": None}})
    rec = match.iloc[0]
    sample_rows = samples[samples["batch_no"] == int(batch_no)]
    feat = features[features["batch_key"] == batch_key]
    model = load_latest()
    train_keys = set(model.get("yield", {}).get("split_keys", {}).get("train", []) if False else [])
    manifest_path_keys = _train_keys()
    return {
        "batch_key": batch_key,
        "machine_id": int(rec["machine_id"]),
        "batch_no": int(rec["batch_no"]),
        "started_at": _iso(rec["started_at"]),
        "ended_at": _iso(rec["ended_at"]),
        "total_duration_min": _none(rec["total_duration_min"]),
        "phases": [_phase(row) for row in phases.to_dict("records")],
        "features": {} if feat.empty else _clean(feat.iloc[0].to_dict()),
        "yields": {
            "measured": {
                "oil_yield_pct": None if feat.empty else _none(feat.iloc[0]["oil_yield_pct"]),
                "carbon_yield_pct": None if feat.empty else _none(feat.iloc[0]["carbon_yield_pct"]),
                "steel_yield_pct": None if feat.empty else _none(feat.iloc[0]["steel_yield_pct"]),
            },
            "predicted": None,
            "in_training_split": batch_key in manifest_path_keys,
        },
        "model_fits": {},
        "residuals": [],
        "detector_events": [],
        "panel_alarm_events": [],
        "samples": [_sample(row) for row in sample_rows.to_dict("records")],
        "quality_flags": _as_list(rec["quality_flags"]),
    }


@router.get("/data/coverage")
def coverage() -> dict:
    con = _con()
    daily = daily_coverage(con)
    gap_frame = gaps(con)
    summary = machine_summaries(con)
    batches = load_batches(con)
    features = load_features(con)
    failures = ingest_failures(con)
    unmapped = unmapped_values(con)
    intervals = machine_intervals(con)
    con.close()
    interval_ix = {}
    if not intervals.empty:
        interval_ix = {int(row.machine_id): row.median_interval_s for row in intervals.itertuples(index=False)}
    per = []
    for rec in summary.to_dict("records") if not summary.empty else []:
        mid = int(rec["machine_id"])
        days = daily[daily["machine_id"] == mid] if not daily.empty else pd.DataFrame()
        machine_gaps = gap_frame[gap_frame["machine_id"] == mid] if not gap_frame.empty else pd.DataFrame()
        per.append({
            "machine_id": mid,
            "history_floor": _iso(rec["history_floor"]),
            "last_sample_at": _iso(rec["last_sample_at"]),
            "n_samples": int(rec["n_samples"]),
            "median_interval_s": _none(interval_ix.get(mid)),
            "daily": [
                {
                    "date": str(row["day"]),
                    "n_samples": int(row["n_samples"]),
                    "median_interval_s": _none(row.get("median_interval_s")),
                    "max_gap_s": _none(row.get("max_gap_s")),
                }
                for row in days.to_dict("records")
            ],
            "gaps": [
                {"from": _iso(row["gap_from"]), "to": _iso(row["gap_to"]), "duration_s": row["duration_s"]}
                for row in machine_gaps.to_dict("records")
            ],
        })
    usable = 0
    with_fault = 0
    complete = 0
    with_excel = 0
    if not features.empty and "usable_for_training" in features.columns:
        usable = int(features["usable_for_training"].fillna(False).astype(bool).sum())
    if not batches.empty:
        complete = int(batches["is_complete"].sum())
        with_fault = int(batches["had_fault"].sum())
        with_excel = sum("no_excel_log" not in _as_list(flags) for flags in batches["quality_flags"])
    return {
        "per_machine": per,
        "batches": {
            "total": 0 if batches.empty else int(len(batches)),
            "complete": complete,
            "usable_for_training": usable,
            "with_excel_log": with_excel,
            "with_fault": with_fault,
        },
        "excel": {"rows_parsed": 0, "rows_unmatched": 0, "unmatched_detail": [], "closure_error_pct": {}},
        "unmapped_process_values": unmapped.to_dict("records") if not unmapped.empty else [],
        "ingest_failures": failures.to_dict("records") if not failures.empty else [],
    }


@router.post("/ingest/excel")
async def ingest_excel(file: UploadFile) -> dict:
    target = ROOT / "data" / "excel_drop" / (file.filename or "upload.xlsx")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(await file.read())
    try:
        entries = parse_workbook(target)
    except ExcelMapError as exc:
        raise HTTPException(status_code=422, detail={"error": {"code": "excel_map", "message": str(exc), "detail": None}}) from exc
    con = _con()
    matched, unmatched = resolve_batch_numbers(con, entries)
    inserted, updated = upsert_batch_log(con, matched)
    con.close()
    stats = assemble()
    return {
        "rows_parsed": len(entries),
        "rows_matched": len(matched),
        "rows_unmatched": len(unmatched),
        "unmatched_detail": unmatched,
        "rows_inserted": inserted,
        "rows_updated": updated,
        "build": stats,
    }


def _train_keys() -> set[str]:
    from htpp.config import settings
    import json
    path = settings.artifacts / "LATEST"
    if not path.exists():
        return set()
    version = path.read_text(encoding="utf-8").strip()
    manifest = settings.artifacts / version / "split_manifest.json"
    if not manifest.exists():
        return set()
    data = json.loads(manifest.read_text(encoding="utf-8"))
    return set(data.get("train", []))


def _sample(row: dict) -> dict:
    return {
        "sampled_at": _iso(row["sampled_at"]),
        "batch_no": None if pd.isna(row["batch_no"]) else int(row["batch_no"]),
        "ts_c": _none(row["ts_c"]),
        "tr_c": _none(row["tr_c"]),
        "ps_bar": _none(row["ps_bar"]),
        "pr_bar": _none(row["pr_bar"]),
        "amb_temp_c": _none(row["amb_temp_c"]),
        "roh_c_per_min": _none(row["roh_c_per_min"]),
        "process_state": row.get("process_state"),
        "process_raw": row.get("process_raw"),
        "fault_state": row.get("fault_state"),
    }


def _phase(row: dict) -> dict:
    return {
        "phase_index": int(row["phase_index"]),
        "process_state": row["process_state"],
        "started_at": _iso(row["started_at"]),
        "ended_at": _iso(row["ended_at"]),
        "duration_min": _none(row["duration_min"]),
        "tr_start_c": _none(row["tr_start_c"]),
        "tr_end_c": _none(row["tr_end_c"]),
        "tr_peak_c": _none(row["tr_peak_c"]),
        "mean_roh_c_per_min": _none(row["mean_roh_c_per_min"]),
    }


def _lttb(samples: list[dict], threshold: int) -> list[dict]:
    if threshold < 3 or len(samples) <= threshold:
        return samples
    bucket = (len(samples) - 2) / (threshold - 2)
    out = [samples[0]]
    a = 0
    for i in range(threshold - 2):
        start = int((i + 1) * bucket) + 1
        end = int((i + 2) * bucket) + 1
        end = min(end, len(samples))
        avg_x = (start + end) / 2
        chunk = samples[start:end] or [samples[-1]]
        avg_y = sum((s["tr_c"] or 0) for s in chunk) / len(chunk)
        best = start
        best_area = -1.0
        ax, ay = a, samples[a]["tr_c"] or 0
        for j in range(int(i * bucket) + 1, start):
            area = abs((ax - avg_x) * ((samples[j]["tr_c"] or 0) - ay) - (ax - j) * (avg_y - ay))
            if area > best_area:
                best_area = area
                best = j
        out.append(samples[best])
        a = best
    out.append(samples[-1])
    return out


def _as_list(value) -> list:
    if value is None:
        return []
    try:
        if pd.isna(value):
            return []
    except (TypeError, ValueError):
        pass
    return [item for item in list(value)]


def _iso(value) -> str | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    stamp = pd.Timestamp(value)
    if stamp.tzinfo is None:
        stamp = stamp.tz_localize("UTC")
    return stamp.tz_convert("UTC").isoformat()


def _parse(value: str | None) -> datetime | None:
    if not value:
        return None
    stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp


def _none(value):
    """JSON-safe value. Arrays must not go through pd.isna (that raises ValueError)."""
    if value is None:
        return None
    if isinstance(value, dict):
        return {str(key): _none(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_none(item) for item in value]
    if isinstance(value, (str, bytes)):
        return value
    if isinstance(value, datetime):
        return _iso(value)
    tolist = getattr(value, "tolist", None)
    if callable(tolist):
        return _none(tolist())
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        return value
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    return value


def _clean(row: dict) -> dict:
    return {key: _none(value) for key, value in row.items()}
