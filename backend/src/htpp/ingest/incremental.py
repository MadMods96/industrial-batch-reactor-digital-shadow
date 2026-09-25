"""One incremental tick. Errors are returned, never allowed to kill the API."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from htpp.config import settings
from htpp.ingest.panel_client import PanelClient
from htpp.ingest.panel_parser import parse_telemetry_table
from htpp.store.db import connect, migrate
from htpp.store.queries import max_sampled_at
from htpp.store.writes import record_ingest_run, upsert_telemetry

log = logging.getLogger("htpp.incremental")
KOLKATA = ZoneInfo("Asia/Kolkata")


async def incremental_tick(machine_ids: list[int] | None = None) -> dict[str, int]:
    ids = machine_ids or settings.machine_ids
    client = PanelClient()
    con = migrate(connect())
    inserted_total = 0
    try:
        for machine_id in ids:
            started = datetime.now(timezone.utc)
            error = None
            fetched = 0
            inserted = 0
            now_local = datetime.now(KOLKATA)
            latest = max_sampled_at(con, machine_id)
            if latest is None:
                start = now_local - timedelta(hours=24)
            else:
                start = latest.astimezone(KOLKATA) - timedelta(minutes=30)
            params = {
                "date": start.date().isoformat(),
                "date1": now_local.date().isoformat(),
                "time": start.strftime("%H:%M"),
                "time1": now_local.strftime("%H:%M"),
                "machineid": str(machine_id),
                "submit": "Submit",
            }
            try:
                html = await client.get("/graph.php", params)
                rows = parse_telemetry_table(html, machine_id, f"{settings.panel_base_url}/graph.php")
                fetched = len(rows)
                inserted = upsert_telemetry(con, rows)
                inserted_total += inserted
            except Exception as exc:  # noqa: BLE001
                error = f"{type(exc).__name__}: {exc}"
                log.exception("incremental tick failed machine=%s", machine_id)
            record_ingest_run(
                con,
                run_id=str(uuid.uuid4()),
                kind="incremental",
                machine_id=machine_id,
                range_start=start.astimezone(timezone.utc),
                range_end=now_local.astimezone(timezone.utc),
                rows_fetched=fetched,
                rows_inserted=inserted,
                http_status=200 if error is None else 0,
                error=error,
                duration_s=(datetime.now(timezone.utc) - started).total_seconds(),
                started_at=started,
            )
    finally:
        await client.aclose()
        con.close()
    return {"rows_inserted": inserted_total}
