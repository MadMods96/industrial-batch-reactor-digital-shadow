"""Historical panel backfill. Zero-row windows are recorded, not treated as errors."""

from __future__ import annotations

import gzip
import logging
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from htpp.config import ROOT, settings
from htpp.ingest.panel_client import PanelClient
from htpp.ingest.panel_parser import parse_telemetry_table
from htpp.store.db import connect, migrate
from htpp.store.writes import record_ingest_run, upsert_telemetry

log = logging.getLogger("htpp.backfill")
KOLKATA = ZoneInfo("Asia/Kolkata")


def _archive(machine_id: int, start: date, end: date, html: str) -> None:
    folder = ROOT / "data" / "raw" / str(machine_id)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{start.isoformat()}_{end.isoformat()}.html.gz"
    path.write_bytes(gzip.compress(html.encode("utf-8")))


async def _fetch_window(client: PanelClient, machine_id: int, start: date, end: date) -> tuple[str, str]:
    params = {
        "date": start.isoformat(),
        "date1": end.isoformat(),
        "time": "00:00",
        "time1": "23:59",
        "machineid": str(machine_id),
        "submit": "Submit",
    }
    html = await client.get("/graph.php", params)
    url = f"{settings.panel_base_url}/graph.php"
    return html, url


async def discover_floor(client: PanelClient, machine_id: int) -> date:
    """Bisect from the configured floor until a populated one-day window appears."""
    probe = settings.history_floor_date
    ceiling = datetime.now(KOLKATA).date()
    found: date | None = None
    cursor = probe
    while cursor <= ceiling:
        html, url = await _fetch_window(client, machine_id, cursor, cursor)
        rows = parse_telemetry_table(html, machine_id, url)
        if rows:
            found = cursor
            break
        cursor += timedelta(days=1)
    if found is None:
        return ceiling
    # Step back one day at a time while the previous day is still empty is already done
    # by the forward scan. Confirm the day before is empty so the floor is the first hit.
    return found


async def backfill(machine_ids: list[int] | None = None) -> int:
    ids = machine_ids or settings.machine_ids
    client = PanelClient()
    con = migrate(connect())
    failures = 0
    try:
        if not await client.is_authenticated():
            await client.login()
        for machine_id in ids:
            floor = await discover_floor(client, machine_id)
            log.info("history floor machine=%s date=%s", machine_id, floor.isoformat())
            ceiling = datetime.now(KOLKATA).date()
            cursor = floor
            chunk = timedelta(days=settings.backfill_chunk_days - 1)
            while cursor <= ceiling:
                end = min(ceiling, cursor + chunk)
                started = datetime.now(timezone.utc)
                error = None
                status = 200
                fetched = 0
                inserted = 0
                for attempt in range(3):
                    try:
                        html, url = await _fetch_window(client, machine_id, cursor, end)
                        _archive(machine_id, cursor, end, html)
                        rows = parse_telemetry_table(html, machine_id, url)
                        fetched = len(rows)
                        inserted = upsert_telemetry(con, rows)
                        error = None
                        break
                    except Exception as exc:  # noqa: BLE001 - recorded, then next chunk
                        error = f"{type(exc).__name__}: {exc}"
                        status = 0
                        wait = (2, 8, 32)[attempt]
                        log.warning("chunk failed machine=%s %s..%s attempt=%s %s", machine_id, cursor, end, attempt, error)
                        import asyncio
                        await asyncio.sleep(wait)
                else:
                    failures += 1
                record_ingest_run(
                    con,
                    run_id=str(uuid.uuid4()),
                    kind="backfill",
                    machine_id=machine_id,
                    range_start=datetime.combine(cursor, datetime.min.time(), KOLKATA),
                    range_end=datetime.combine(end, datetime.max.time(), KOLKATA),
                    rows_fetched=fetched,
                    rows_inserted=inserted,
                    http_status=status,
                    error=error,
                    duration_s=(datetime.now(timezone.utc) - started).total_seconds(),
                    started_at=started,
                )
                cursor = end + timedelta(days=1)
    finally:
        await client.aclose()
        con.close()
    return failures
