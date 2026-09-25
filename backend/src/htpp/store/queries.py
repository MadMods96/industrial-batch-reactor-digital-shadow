"""Every SQL statement in the project lives here."""

from __future__ import annotations

from datetime import datetime

import duckdb
import pandas as pd
import pytz  # noqa: F401 — DuckDB refuses TIMESTAMPTZ values unless pytz is installed


def telemetry_count(con: duckdb.DuckDBPyConnection) -> int:
    return int(con.execute("SELECT COUNT(*) FROM telemetry_raw").fetchone()[0])


def max_sampled_at(con: duckdb.DuckDBPyConnection, machine_id: int) -> datetime | None:
    row = con.execute(
        "SELECT MAX(sampled_at) FROM telemetry_raw WHERE machine_id = ?",
        [machine_id],
    ).fetchone()
    return row[0] if row else None


def load_telemetry(
    con: duckdb.DuckDBPyConnection,
    machine_id: int | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
) -> pd.DataFrame:
    clauses = ["1=1"]
    params: list[object] = []
    if machine_id is not None:
        clauses.append("machine_id = ?")
        params.append(machine_id)
    if start is not None:
        clauses.append("sampled_at >= ?")
        params.append(start)
    if end is not None:
        clauses.append("sampled_at <= ?")
        params.append(end)
    where = " AND ".join(clauses)
    return con.execute(
        f"SELECT * FROM telemetry_raw WHERE {where} ORDER BY machine_id, sampled_at",
        params,
    ).df()


def load_batches(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    return con.execute("SELECT * FROM batches ORDER BY started_at").df()


def load_phases(con: duckdb.DuckDBPyConnection, batch_key: str | None = None) -> pd.DataFrame:
    if batch_key:
        return con.execute(
            "SELECT * FROM phases WHERE batch_key = ? ORDER BY phase_index",
            [batch_key],
        ).df()
    return con.execute("SELECT * FROM phases ORDER BY batch_key, phase_index").df()


def load_features(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    return con.execute("SELECT * FROM batch_features ORDER BY started_at").df()


def load_yields(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    return con.execute("SELECT * FROM batch_yields").df()


def load_batch_log(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    return con.execute("SELECT * FROM batch_log").df()


def latest_per_machine(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    return con.execute(
        """
        SELECT t.*
        FROM telemetry_raw t
        JOIN (
            SELECT machine_id, MAX(sampled_at) AS sampled_at
            FROM telemetry_raw
            GROUP BY machine_id
        ) m ON t.machine_id = m.machine_id AND t.sampled_at = m.sampled_at
        ORDER BY t.machine_id
        """
    ).df()


def machine_summaries(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    return con.execute(
        """
        SELECT
            t.machine_id,
            MIN(t.sampled_at) AS history_floor,
            MAX(t.sampled_at) AS last_sample_at,
            COUNT(*) AS n_samples,
            ANY_VALUE(t.panel_chip_id) AS panel_chip_id,
            ANY_VALUE(t.panel_version) AS panel_version
        FROM telemetry_raw t
        GROUP BY t.machine_id
        ORDER BY t.machine_id
        """
    ).df()


def batch_counts(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    return con.execute(
        """
        SELECT machine_id,
               COUNT(*) AS n_batches,
               SUM(CASE WHEN is_complete THEN 1 ELSE 0 END) AS n_batches_complete
        FROM batches
        GROUP BY machine_id
        """
    ).df()


def daily_coverage(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    return con.execute(
        """
        WITH ordered AS (
            SELECT machine_id,
                   CAST(sampled_at AT TIME ZONE 'Asia/Kolkata' AS DATE) AS day,
                   EPOCH(sampled_at - LAG(sampled_at) OVER (
                       PARTITION BY machine_id,
                                    CAST(sampled_at AT TIME ZONE 'Asia/Kolkata' AS DATE)
                       ORDER BY sampled_at
                   )) AS dt_s
            FROM telemetry_raw
        )
        SELECT machine_id,
               day,
               COUNT(*) AS n_samples,
               MEDIAN(dt_s) AS median_interval_s,
               MAX(dt_s) AS max_gap_s
        FROM ordered
        GROUP BY 1, 2
        ORDER BY 1, 2
        """
    ).df()


def machine_intervals(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    return con.execute(
        """
        WITH ordered AS (
            SELECT machine_id,
                   EPOCH(sampled_at - LAG(sampled_at) OVER (
                       PARTITION BY machine_id ORDER BY sampled_at
                   )) AS dt_s
            FROM telemetry_raw
        )
        SELECT machine_id, MEDIAN(dt_s) AS median_interval_s
        FROM ordered
        WHERE dt_s IS NOT NULL
        GROUP BY machine_id
        """
    ).df()


def gaps(con: duckdb.DuckDBPyConnection, min_gap_s: float = 1800) -> pd.DataFrame:
    return con.execute(
        """
        WITH ordered AS (
            SELECT machine_id, sampled_at,
                   LAG(sampled_at) OVER (PARTITION BY machine_id ORDER BY sampled_at) AS prev
            FROM telemetry_raw
        )
        SELECT machine_id, prev AS gap_from, sampled_at AS gap_to,
               EPOCH(sampled_at - prev) AS duration_s
        FROM ordered
        WHERE prev IS NOT NULL AND EPOCH(sampled_at - prev) > ?
        ORDER BY duration_s DESC
        """,
        [min_gap_s],
    ).df()


def ingest_failures(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    return con.execute(
        """
        SELECT * FROM ingest_runs
        WHERE error IS NOT NULL
        ORDER BY started_at DESC
        LIMIT 50
        """
    ).df()


def unmapped_values(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    return con.execute(
        """
        SELECT process_raw, COUNT(*) AS n
        FROM unmapped_process
        GROUP BY process_raw
        ORDER BY n DESC
        """
    ).df()


def flag_counts(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    return con.execute(
        """
        SELECT UNNEST(quality_flags) AS flag, COUNT(*) AS n
        FROM batches
        GROUP BY 1
        ORDER BY n DESC
        """
    ).df()


def last_ingest(con: duckdb.DuckDBPyConnection) -> tuple | None:
    return con.execute(
        """
        SELECT started_at, CASE WHEN error IS NULL THEN 'ok' ELSE 'error' END
        FROM ingest_runs
        ORDER BY started_at DESC
        LIMIT 1
        """
    ).fetchone()


def consecutive_failures(con: duckdb.DuckDBPyConnection) -> int:
    rows = con.execute(
        """
        SELECT error FROM ingest_runs
        WHERE kind = 'incremental'
        ORDER BY started_at DESC
        LIMIT 10
        """
    ).fetchall()
    count = 0
    for (error,) in rows:
        if error:
            count += 1
        else:
            break
    return count
