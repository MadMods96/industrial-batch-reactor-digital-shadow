"""Loud checks run at the end of `make build`. NULL is allowed. Sentinels are not."""

from __future__ import annotations

import duckdb


class BatchIntegrityError(RuntimeError):
    pass


def assert_batches_valid(con: duckdb.DuckDBPyConnection) -> None:
    bad_batches = con.execute(
        """
        SELECT batch_key, peak_tr_c, n_samples, total_duration_min
        FROM batches
        WHERE (peak_tr_c IS NOT NULL AND (peak_tr_c < 0 OR peak_tr_c > 900))
           OR n_samples < 1
           OR (total_duration_min IS NOT NULL AND total_duration_min < 0)
        """
    ).fetchall()
    bad_phases = con.execute(
        """
        SELECT batch_key, phase_index, duration_min
        FROM phases
        WHERE duration_min IS NOT NULL AND duration_min < 0
        """
    ).fetchall()
    if bad_batches or bad_phases:
        raise BatchIntegrityError(f"batches={bad_batches} phases={bad_phases}")
