"""Build a compact plant briefing for the assistant. Numbers come from DuckDB only."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pandas as pd

from htpp.store.db import connect, migrate
from htpp.store.queries import gaps, load_batches, load_features, machine_summaries, unmapped_values


def plant_briefing(max_batches: int = 40) -> dict:
    con = migrate(connect())
    try:
        summary = machine_summaries(con)
        batches = load_batches(con)
        features = load_features(con)
        gap_frame = gaps(con)
        unmapped = unmapped_values(con)
        logs = con.execute(
            """
            SELECT machine_id, batch_no, log_date, feed_mass_kg, moisture_pct,
                   feedstock_type, oil_mass_kg, carbon_mass_kg, steel_mass_kg, gas_mass_kg
            FROM batch_log
            ORDER BY log_date DESC NULLS LAST
            LIMIT 80
            """
        ).df()
        yields = con.execute(
            """
            SELECT machine_id, batch_no, oil_yield_pct, carbon_yield_pct, steel_yield_pct,
                   gas_yield_pct, closure_error_pct, accounted_pct
            FROM batch_yields
            ORDER BY machine_id, batch_no
            """
        ).df()
    finally:
        con.close()

    feat = features.set_index("batch_key") if not features.empty else pd.DataFrame()
    recent = []
    if not batches.empty:
        ordered = batches.sort_values("started_at", ascending=False).head(max_batches)
        for rec in ordered.to_dict("records"):
            extra = feat.loc[rec["batch_key"]].to_dict() if rec["batch_key"] in getattr(feat, "index", []) else {}
            recent.append({
                "batch_key": rec["batch_key"],
                "started_at": _iso(rec["started_at"]),
                "duration_min": _num(rec.get("total_duration_min")),
                "peak_tr_c": _num(rec.get("peak_tr_c")),
                "had_fault": bool(_num(rec.get("had_fault")) or False) if rec.get("had_fault") is not None else False,
                "usable_for_training": bool(extra.get("usable_for_training") or False),
                "oil_yield_pct": _num(extra.get("oil_yield_pct")),
                "carbon_yield_pct": _num(extra.get("carbon_yield_pct")),
                "steel_yield_pct": _num(extra.get("steel_yield_pct")),
                "feed_mass_kg": _num(extra.get("feed_mass_kg")),
                "moisture_pct": _num(extra.get("moisture_pct")),
                "quality_flags": _flags(rec.get("quality_flags")),
            })

    yield_summary = {}
    if not yields.empty:
        for col in ("oil_yield_pct", "carbon_yield_pct", "steel_yield_pct", "closure_error_pct"):
            series = pd.to_numeric(yields[col], errors="coerce").dropna()
            if not series.empty:
                yield_summary[col] = {
                    "n": int(len(series)),
                    "median": round(float(series.median()), 2),
                    "p10": round(float(series.quantile(0.1)), 2),
                    "p90": round(float(series.quantile(0.9)), 2),
                }

    machines = []
    if not summary.empty:
        for rec in summary.to_dict("records"):
            machines.append({
                "machine_id": int(rec["machine_id"]),
                "n_samples": int(rec["n_samples"]),
                "history_floor": _iso(rec["history_floor"]),
                "last_sample_at": _iso(rec["last_sample_at"]),
            })

    gap_list = []
    if not gap_frame.empty:
        for rec in gap_frame.sort_values("duration_s", ascending=False).head(12).to_dict("records"):
            gap_list.append({
                "machine_id": int(rec["machine_id"]),
                "from": _iso(rec["gap_from"]),
                "to": _iso(rec["gap_to"]),
                "duration_h": round(float(rec["duration_s"]) / 3600.0, 1),
            })

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "machines": machines,
        "batch_counts": {
            "total": 0 if batches.empty else int(len(batches)),
            "with_excel": 0 if features.empty else int((~features["oil_yield_pct"].isna()).sum()) if "oil_yield_pct" in features.columns else 0,
            "usable_for_training": 0 if features.empty else int(features["usable_for_training"].fillna(False).astype(bool).sum()),
            "excel_log_rows": 0 if logs.empty else int(len(logs)),
            "yield_rows": 0 if yields.empty else int(len(yields)),
        },
        "yield_summary": yield_summary,
        "recent_batches": recent,
        "largest_gaps": gap_list,
        "unmapped_process_values": unmapped.to_dict("records") if not unmapped.empty else [],
        "excel_sample": [
            {key: _num(value) if key != "feedstock_type" and key != "log_date" else (None if value is None else str(value))
             for key, value in row.items()}
            for row in (logs.head(15).to_dict("records") if not logs.empty else [])
        ],
    }


def briefing_text(briefing: dict | None = None) -> str:
    data = briefing or plant_briefing()
    return json.dumps(data, default=str, indent=2)


def rule_insights(briefing: dict | None = None) -> list[dict]:
    """Deterministic alerts in plain plant language for operators."""
    data = briefing or plant_briefing()
    out: list[dict] = []
    counts = data.get("batch_counts") or {}
    if counts.get("excel_log_rows", 0) == 0:
        out.append({
            "severity": "warning",
            "title": "Plant Excel log not loaded",
            "detail": "Oil and carbon yield numbers are missing until the plant Excel sheet is matched to panel batches.",
        })
    else:
        matched = int(counts.get("excel_log_rows", 0) or 0)
        with_yield = int(counts.get("yield_rows", 0) or 0)
        usable = int(counts.get("usable_for_training", 0) or 0)
        out.append({
            "severity": "ok",
            "title": f"{with_yield} batches have oil yield recorded",
            "detail": (
                f"{matched} Excel rows were matched to panel batches. "
                f"{usable} of those look complete enough for yield learning."
            ),
        })
    ys = data.get("yield_summary") or {}
    if "oil_yield_pct" in ys:
        oil = ys["oil_yield_pct"]
        out.append({
            "severity": "ok",
            "title": f"Typical oil yield is about {oil['median']}%",
            "detail": (
                f"From {oil['n']} logged batches, most oil yields sit between "
                f"{oil['p10']}% and {oil['p90']}%. Median is {oil['median']}%."
            ),
        })
    if "closure_error_pct" in ys and ys["closure_error_pct"]["median"] > 20:
        out.append({
            "severity": "warning",
            "title": "Product weights often don't add up",
            "detail": (
                f"On a typical batch, oil + carbon + steel + gas differ from feed by about "
                f"{ys['closure_error_pct']['median']}%. Recheck Loading and weighing against the Excel log."
            ),
        })
    for gap in (data.get("largest_gaps") or [])[:3]:
        if gap["duration_h"] >= 12:
            name = _machine_name(gap["machine_id"])
            out.append({
                "severity": "critical" if gap["duration_h"] >= 48 else "warning",
                "title": f"{name} had no panel data for {_human_duration(gap['duration_h'])}",
                "detail": (
                    f"The panel stopped sending readings from {_human_when(gap['from'])} "
                    f"until {_human_when(gap['to'])}. This looks like a plant-side gap, not a file import error."
                ),
            })
    for batch in data.get("recent_batches") or []:
        if batch.get("had_fault"):
            key = str(batch.get("batch_key") or "")
            machine_id, _, batch_no = key.partition("-")
            name = _machine_name(int(machine_id)) if machine_id.isdigit() else "A reactor"
            flags = _human_flags(batch.get("quality_flags") or [])
            out.append({
                "severity": "warning",
                "title": f"Fault during {name} batch {batch_no or key}",
                "detail": (
                    f"Batch started {_human_when(batch.get('started_at'))}. "
                    + (flags or "Panel recorded a fault on this run.")
                ),
            })
            break
    stale = []
    now = datetime.now(timezone.utc)
    for machine in data.get("machines") or []:
        stamp = machine.get("last_sample_at")
        if not stamp:
            continue
        last = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        age_min = (now - last).total_seconds() / 60.0
        if age_min > 30:
            stale.append(f"{_machine_name(machine['machine_id'])} (last seen {_human_age(age_min)})")
    if stale:
        out.append({
            "severity": "warning",
            "title": "Live data is stale on some reactors",
            "detail": "No fresh sample for: " + "; ".join(stale),
        })
    if not out:
        out.append({
            "severity": "ok",
            "title": "Plant looks quiet",
            "detail": "No alerts from the current plant snapshot.",
        })
    return out[:8]


def _machine_name(machine_id: int | str) -> str:
    from htpp.plant import machine_label

    try:
        return machine_label(int(machine_id))
    except (TypeError, ValueError):
        return f"Reactor {machine_id}"


def _human_when(value: str | None) -> str:
    if not value:
        return "an unknown time"
    try:
        stamp = pd.Timestamp(value)
        if stamp.tzinfo is None:
            stamp = stamp.tz_localize("UTC")
        local = stamp.tz_convert("Asia/Kolkata")
        hour = local.hour % 12 or 12
        ampm = "am" if local.hour < 12 else "pm"
        return f"{local.day} {local.strftime('%b %Y')}, {hour}:{local.strftime('%M')} {ampm} IST"
    except Exception:  # noqa: BLE001
        return str(value)


def _human_duration(hours: float) -> str:
    h = float(hours)
    if h >= 48:
        days = h / 24.0
        return f"about {days:.1f} days"
    if h >= 24:
        return f"about {h / 24.0:.1f} days"
    if h >= 1:
        return f"about {h:.0f} hours"
    return f"about {max(1, int(h * 60))} minutes"


def _human_age(minutes: float) -> str:
    if minutes >= 1440:
        return f"{minutes / 1440:.1f} days ago"
    if minutes >= 60:
        return f"{minutes / 60:.0f} hours ago"
    return f"{minutes:.0f} min ago"


def _human_flags(flags: list[str]) -> str:
    labels = {
        "no_excel_log": "no Excel yield log for this batch",
        "had_fault": "panel reported a fault",
        "mass_balance_impossible": "oil/carbon/steel weights do not add up to feed",
        "mass_balance_open": "product weights leave a large open balance",
        "ingestion_gap": "panel data had a long silence during the batch",
        "unknown_process_state": "panel sent an unknown process label",
        "missing_terminal": "batch may be missing a clear end state",
    }
    parts = [labels.get(flag, flag.replace("_", " ")) for flag in flags]
    if not parts:
        return ""
    if len(parts) == 1:
        return f"Note: {parts[0]}."
    return "Notes: " + "; ".join(parts) + "."


def _flags(value) -> list[str]:
    if value is None:
        return []
    try:
        if pd.isna(value):
            return []
    except (TypeError, ValueError):
        pass
    return [str(item) for item in list(value)]


def _iso(value) -> str | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    stamp = pd.Timestamp(value)
    if stamp.tzinfo is None:
        stamp = stamp.tz_localize("UTC")
    return stamp.tz_convert("UTC").isoformat()


def _num(value):
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    try:
        return float(value)
    except (TypeError, ValueError):
        return value
