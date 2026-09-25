"""Synthetic telemetry and batch log, used only until the plant file arrives.

Rows are labelled source_file='synthetic_batch_log.xlsx'. Do not report them as findings.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from openpyxl import Workbook

from htpp.config import ROOT
from htpp.schemas import TelemetrySample
from htpp.store.db import connect, migrate
from htpp.store.writes import upsert_batch_log, upsert_telemetry
from htpp.ingest.excel_log import parse_workbook

SLOT = 240  # seconds, the observed cadence
PHASES_833 = [
    ("heating", datetime(2026, 9, 18, 0, 17, 4, tzinfo=timezone.utc)),
    ("gas", datetime(2026, 9, 18, 2, 0, 33, tzinfo=timezone.utc)),
    ("cooling", datetime(2026, 9, 18, 8, 34, 41, tzinfo=timezone.utc)),
    ("n2_purging", datetime(2026, 9, 18, 12, 51, 1, tzinfo=timezone.utc)),
    ("carbon_discharge", datetime(2026, 9, 18, 16, 31, 35, tzinfo=timezone.utc)),
    ("main_door_open", datetime(2026, 9, 18, 19, 22, 21, tzinfo=timezone.utc)),
]
END_833 = datetime(2026, 9, 19, 2, 34, 4, tzinfo=timezone.utc)
RAW = {
    "heating": "HEATING",
    "gas": "GAS",
    "cooling": "COOLING",
    "n2_purging": "N2 PURGING",
    "carbon_discharge": "CARBON DISCHARGE",
    "main_door_open": "MAIN DOOR OPEN",
    "idle": "Machine Idle",
}


def seed(force: bool = False) -> int:
    con = migrate(connect())
    existing = con.execute("SELECT COUNT(*) FROM telemetry_raw").fetchone()[0]
    if existing and not force:
        con.close()
        return 0
    rows: list[TelemetrySample] = []
    rows.extend(_batch_833())
    rng = np.random.default_rng(19)
    for machine_id, start_no in ((1093, 820), (1094, 410), (1146, 210)):
        for offset in range(8):
            batch_no = start_no + offset
            if machine_id == 1093 and batch_no == 833:
                continue
            start = datetime(2026, 8, 16, tzinfo=timezone.utc) + timedelta(days=offset * 3, hours=machine_id % 5)
            rows.extend(_synthetic_batch(machine_id, batch_no, start, rng))
    inserted = upsert_telemetry(con, rows)
    xlsx = _write_excel(rows)
    from htpp.store.writes import upsert_batch_log as _up
    entries = parse_workbook(xlsx)
    _up(con, entries)
    con.close()
    return inserted


def _batch_833() -> list[TelemetrySample]:
    bounds = PHASES_833 + [("end", END_833)]
    rows = []
    cursor = bounds[0][1]
    index = 0
    tr = 34.0
    while cursor < END_833:
        while index + 1 < len(bounds) and cursor >= bounds[index + 1][1]:
            index += 1
        state = bounds[index][0]
        if state == "heating":
            tr = min(455.0, tr + 8.5)
        elif state == "gas":
            tr = 450.0 + 4.0 * np.sin((cursor - bounds[2][1]).total_seconds() / 4000)
        elif state in {"cooling", "n2_purging", "carbon_discharge", "main_door_open"}:
            tr = 30.0 + (tr - 30.0) * np.exp(-SLOT / (200 * 60))
        rows.append(_sample(1093, 833, cursor, state, tr, 0.15 if state == "gas" else 0.0))
        cursor += timedelta(seconds=SLOT)
    return rows


def _synthetic_batch(machine_id: int, batch_no: int, start: datetime, rng: np.random.Generator) -> list[TelemetrySample]:
    tau_min = 160 + (batch_no % 7) * 12 + machine_id % 10
    peak = 430 + (batch_no % 5) * 8
    plan = [("heating", 26), ("gas", 40), ("cooling", 36), ("n2_purging", 12), ("carbon_discharge", 10), ("main_door_open", 6)]
    if batch_no % 9 == 0:
        plan.insert(2, ("gas", 2))  # fault window sits inside gas via process_raw override below
    rows = []
    tr = 32.0
    cursor = start
    fault_at = 20
    step = 0
    for state, count in plan:
        for i in range(count):
            if state == "heating":
                tr += (peak - tr) * 0.18
            elif state == "gas":
                tr += rng.normal(0, 0.4)
            else:
                tr = 29.0 + (tr - 29.0) * np.exp(-SLOT / (tau_min * 60))
            raw_state = state
            fault = "none"
            if state == "gas" and i == fault_at and batch_no % 9 == 0:
                raw_state = "choke"
                fault = "gas_passage_choke"
            rows.append(_sample(machine_id, batch_no, cursor, raw_state if raw_state != "choke" else "gas", tr, 0.1 if state == "gas" else 0.0, fault if raw_state == "choke" else None))
            cursor += timedelta(seconds=SLOT)
            step += 1
    return rows


def _sample(machine_id, batch_no, when, state, tr, pr, fault: str | None = None) -> TelemetrySample:
    from htpp.schemas import FaultState, ProcessState
    return TelemetrySample(
        machine_id=machine_id,
        sampled_at=when,
        batch_no=batch_no,
        ts_c=round(min(tr * 0.45, 210), 1),
        tr_c=round(float(tr), 1),
        ps_bar=0.0,
        pr_bar=round(pr, 3),
        process_raw="Gas Passage Choke" if fault else RAW[state],
        process_state=ProcessState(state),
        fault_state=FaultState(fault or "none"),
        roh_c_per_min=2.4 if state == "heating" else 0.1,
        roh_cal_c_per_min=2.2 if state == "heating" else 0.1,
        amb_temp_c=28.5,
        panel_version="427.2",
        panel_chip_id="14313288" if machine_id == 1093 else str(14000000 + machine_id),
        ingested_at=datetime.now(timezone.utc),
        source_url="synthetic://fixture",
    )


def _write_excel(rows: list[TelemetrySample]) -> Path:
    seen = {}
    for row in rows:
        seen[(row.machine_id, row.batch_no)] = row
    path = ROOT / "backend" / "tests" / "fixtures" / "batch_log.xlsx"
    path.parent.mkdir(parents=True, exist_ok=True)
    book = Workbook()
    sheet = book.active
    sheet.title = "Batch Log"
    sheet.append(["Machine", "Batch No", "Date", "Input (kg)", "Moisture %", "Material", "Oil (kg)", "Carbon (kg)", "Steel (kg)", "Gas (kg)", "Operator", "Notes"])
    names = {1093: "R1 Unit 1", 1094: "R2 Unit 2", 1146: "R3 Unit 3"}
    for i, ((machine_id, batch_no), row) in enumerate(sorted(seen.items())):
        feed = 5000 + (batch_no % 11) * 120
        moisture = 1.5 + (batch_no % 4) * 0.4
        mix = batch_no % 5 == 0
        oil = feed * (0.36 + (row.tr_c or 400) / 20000)
        carbon = feed * 0.31
        steel = feed * (0.16 if mix else 0.12)
        gas = None if i % 7 else feed * 0.08
        if i == 3:
            oil = feed * 0.7  # impossible closure
        if i == 4:
            gas = feed * 0.02
            oil = feed * 0.2  # open balance with gas present
        sheet.append([
            names[machine_id], batch_no, row.sampled_at.date().isoformat(), feed, round(moisture, 2),
            "tyre_plastic_mix" if mix else "tyre", round(oil, 1), round(carbon, 1), round(steel, 1),
            gas, "A" if batch_no % 2 == 0 else "B", "synthetic fixture, not a plant log",
        ])
    # One unresolvable name is a hard failure, so it stays out of the happy-path file.
    book.save(path)
    drop = ROOT / "data" / "excel_drop" / "synthetic_batch_log.xlsx"
    drop.parent.mkdir(parents=True, exist_ok=True)
    book.save(drop)
    return path
