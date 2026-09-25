"""Idempotent writes. Uniqueness of telemetry is (machine_id, sampled_at)."""

from __future__ import annotations

from datetime import datetime, timezone

import duckdb
import pandas as pd

from htpp.schemas import BatchLogEntry, TelemetrySample


def upsert_telemetry(
    con: duckdb.DuckDBPyConnection,
    rows: list[TelemetrySample],
    *,
    refresh: bool = False,
) -> int:
    if not rows:
        return 0
    before = con.execute("SELECT COUNT(*) FROM telemetry_raw").fetchone()[0]
    frame = pd.DataFrame([row.model_dump() for row in rows])
    frame = frame.drop_duplicates(["machine_id", "sampled_at"], keep="last")
    for column in ("sampled_at", "ingested_at"):
        frame[column] = pd.to_datetime(frame[column], utc=True)
    frame["process_state"] = frame["process_state"].map(lambda value: getattr(value, "value", value))
    frame["fault_state"] = frame["fault_state"].map(lambda value: getattr(value, "value", value))
    con.register("_telemetry_in", frame)
    conflict = "DO NOTHING"
    if refresh:
        conflict = """
        DO UPDATE SET
            batch_no = excluded.batch_no,
            ts_c = excluded.ts_c,
            tr_c = excluded.tr_c,
            ps_bar = excluded.ps_bar,
            pr_bar = excluded.pr_bar,
            process_raw = excluded.process_raw,
            process_state = excluded.process_state,
            fault_state = excluded.fault_state,
            roh_c_per_min = excluded.roh_c_per_min,
            roh_cal_c_per_min = excluded.roh_cal_c_per_min,
            amb_temp_c = excluded.amb_temp_c,
            panel_version = excluded.panel_version,
            panel_chip_id = excluded.panel_chip_id
        """
    con.execute(
        f"""
        INSERT INTO telemetry_raw
        SELECT machine_id, sampled_at, batch_no, ts_c, tr_c, ps_bar, pr_bar,
               process_raw, process_state, fault_state, roh_c_per_min,
               roh_cal_c_per_min, amb_temp_c, panel_version, panel_chip_id,
               ingested_at, source_url
        FROM _telemetry_in
        ON CONFLICT (machine_id, sampled_at) {conflict}
        """
    )
    con.unregister("_telemetry_in")
    after = con.execute("SELECT COUNT(*) FROM telemetry_raw").fetchone()[0]
    return int(after - before)


def record_ingest_run(
    con: duckdb.DuckDBPyConnection,
    *,
    run_id: str,
    kind: str,
    machine_id: int | None,
    range_start: datetime | None,
    range_end: datetime | None,
    rows_fetched: int,
    rows_inserted: int,
    http_status: int | None,
    error: str | None,
    duration_s: float,
    started_at: datetime | None = None,
) -> None:
    con.execute(
        """
        INSERT INTO ingest_runs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            run_id,
            kind,
            machine_id,
            range_start,
            range_end,
            rows_fetched,
            rows_inserted,
            http_status,
            error,
            duration_s,
            started_at or datetime.now(timezone.utc),
        ],
    )


def replace_batches(con: duckdb.DuckDBPyConnection, batches: pd.DataFrame, phases: pd.DataFrame) -> None:
    con.execute("DELETE FROM batches")
    con.execute("DELETE FROM phases")
    if not batches.empty:
        con.register("_batches", batches)
        con.execute("INSERT INTO batches SELECT * FROM _batches")
        con.unregister("_batches")
    if not phases.empty:
        con.register("_phases", phases)
        con.execute("INSERT INTO phases SELECT * FROM _phases")
        con.unregister("_phases")


def upsert_batch_log(con: duckdb.DuckDBPyConnection, entries: list[BatchLogEntry]) -> tuple[int, int]:
    inserted = 0
    updated = 0
    for entry in entries:
        exists = con.execute(
            "SELECT 1 FROM batch_log WHERE machine_id = ? AND batch_no = ?",
            [entry.machine_id, entry.batch_no],
        ).fetchone()
        log_date = entry.log_date.date() if entry.log_date else None
        values = [
            entry.machine_id,
            entry.batch_no,
            log_date,
            entry.feed_mass_kg,
            entry.moisture_pct,
            entry.feedstock_type,
            entry.feedstock_mix_pct,
            entry.oil_mass_kg,
            entry.carbon_mass_kg,
            entry.steel_mass_kg,
            entry.gas_mass_kg,
            entry.operator,
            entry.notes,
            entry.source_file,
            entry.source_row,
        ]
        if exists:
            con.execute(
                """
                UPDATE batch_log SET log_date=?, feed_mass_kg=?, moisture_pct=?,
                    feedstock_type=?, feedstock_mix_pct=?, oil_mass_kg=?, carbon_mass_kg=?,
                    steel_mass_kg=?, gas_mass_kg=?, operator=?, notes=?, source_file=?, source_row=?
                WHERE machine_id=? AND batch_no=?
                """,
                values[2:] + values[:2],
            )
            updated += 1
        else:
            con.execute(
                """
                INSERT INTO batch_log VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                values,
            )
            inserted += 1
    return inserted, updated


def replace_yields(con: duckdb.DuckDBPyConnection, frame: pd.DataFrame) -> None:
    con.execute("DELETE FROM batch_yields")
    if frame.empty:
        return
    con.register("_yields", frame)
    con.execute("INSERT INTO batch_yields SELECT * FROM _yields")
    con.unregister("_yields")


def replace_features(con: duckdb.DuckDBPyConnection, frame: pd.DataFrame) -> None:
    con.execute("DELETE FROM batch_features")
    if frame.empty:
        return
    con.register("_features", frame)
    cols = ", ".join(frame.columns)
    con.execute(f"INSERT INTO batch_features ({cols}) SELECT {cols} FROM _features")
    con.unregister("_features")


def log_unmapped(con: duckdb.DuckDBPyConnection, machine_id: int, sampled_at: datetime, raw: str) -> None:
    con.execute(
        "INSERT INTO unmapped_process VALUES (?, ?, ?)",
        [machine_id, sampled_at, raw],
    )
