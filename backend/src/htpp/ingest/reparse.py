"""Re-read archived panel HTML. Does not talk to the panel."""

from __future__ import annotations

import gzip
import logging
from collections import defaultdict
from pathlib import Path

from htpp.config import ROOT
from htpp.ingest.panel_parser import parse_telemetry_table, remap_rows
from htpp.schemas import TelemetrySample
from htpp.store.db import connect, migrate
from htpp.store.writes import upsert_telemetry

log = logging.getLogger("htpp.reparse")


def reparse(raw_dir: Path | None = None) -> int:
    folder = raw_dir or (ROOT / "data" / "raw")
    by_machine: dict[int, list[TelemetrySample]] = defaultdict(list)
    files = sorted(folder.glob("*/*.html.gz"))
    if not files:
        raise FileNotFoundError(f"No archived HTML under {folder}")
    for path in files:
        machine_id = int(path.parent.name)
        html = gzip.decompress(path.read_bytes()).decode("utf-8", errors="replace")
        parsed = parse_telemetry_table(html, machine_id, f"archive://{path.name}")
        by_machine[machine_id].extend(parsed)
        log.info("reparsed %s rows=%s", path.name, len(parsed))
    rows: list[TelemetrySample] = []
    for chunk in by_machine.values():
        latest: dict[tuple[int, object], TelemetrySample] = {}
        for row in chunk:
            latest[(row.machine_id, row.sampled_at)] = row
        rows.extend(remap_rows(list(latest.values())))
    con = migrate(connect())
    try:
        upsert_telemetry(con, rows, refresh=True)
    finally:
        con.close()
    return len(rows)
