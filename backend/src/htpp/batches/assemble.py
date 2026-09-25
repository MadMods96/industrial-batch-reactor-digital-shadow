"""Build derived tables from raw telemetry and the batch log."""

from __future__ import annotations

import pandas as pd

from htpp.batches.features import build_features, compute_yields
from htpp.batches.integrity import assert_batches_valid
from htpp.batches.segment import apply_excel_flags, segment
from htpp.ingest.panel_parser import PROCESS_MAP
from htpp.store.db import connect, migrate
from htpp.store.queries import load_batch_log, load_telemetry
from htpp.store.writes import replace_batches, replace_features, replace_yields


def assemble() -> dict[str, int]:
    con = migrate(connect())
    telemetry = load_telemetry(con)
    logs = load_batch_log(con)
    yields = compute_yields(logs) if not logs.empty else pd.DataFrame()
    batches, phases = segment(telemetry)
    logged = set()
    if not logs.empty:
        logged = {(int(r.machine_id), int(r.batch_no)) for r in logs.itertuples(index=False)}
    if not batches.empty:
        batches = apply_excel_flags(batches, logged, yields)
    features = build_features(telemetry, batches, phases, yields, logs) if not batches.empty else pd.DataFrame()
    con.execute("DELETE FROM unmapped_process")
    known = pd.DataFrame({"key": list(PROCESS_MAP)})
    con.register("_known_process", known)
    con.execute(
        """
        INSERT INTO unmapped_process
        SELECT machine_id, sampled_at, process_raw
        FROM telemetry_raw
        WHERE process_state = 'unknown'
          AND process_raw IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM _known_process k
              WHERE k.key = lower(trim(regexp_replace(process_raw, '\\s+', ' ', 'g')))
          )
        """
    )
    con.unregister("_known_process")
    stored = batches.drop(columns=["usable_for_training"], errors="ignore")
    replace_yields(con, yields)
    replace_batches(con, stored, phases)
    replace_features(con, features)
    assert_batches_valid(con)
    usable = int(features["usable_for_training"].sum()) if not features.empty else 0
    con.close()
    return {
        "batches": int(len(batches)),
        "phases": int(len(phases)),
        "features": int(len(features)),
        "usable_for_training": usable,
    }
