"""Parser contract fixture. Headers are the live panel names."""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from htpp.ingest.panel_client import ForbiddenPathError, PanelClient
from htpp.ingest.panel_parser import SchemaDriftError, parse_telemetry_table
from htpp.models.interpolate import dense_trajectory

KOLKATA = ZoneInfo("Asia/Kolkata")


def _html(rows: list[str]) -> str:
    body = "".join(f"<tr>{r}</tr>" for r in rows)
    return f"""
    <table><thead><tr>
      <th>SN</th><th>Batch No</th><th>Ts</th><th>Tr</th><th>Ps</th><th>Pr</th>
      <th>Process</th><th>ROH</th><th>ROH Cal.</th><th>Amb. Temp.</th>
      <th>Date Time</th><th>Version</th><th>Panel Chip Id</th>
    </tr></thead><tbody>{body}</tbody></table>
    """


def test_parser_headers_and_timezone():
    html = _html([
        "<td>1</td><td>833</td><td>193</td><td>412</td><td>0.02</td><td>0.12</td>"
        "<td>HEATING</td><td>1.4</td><td>1.2</td><td>28.5</td>"
        "<td>2026-09-18 05:47:04</td><td>427.2</td><td>14313288</td>",
        "<td>2</td><td>833</td><td></td><td>410</td><td>0</td><td>OPEN</td>"
        "<td>Choke Emergency</td><td></td><td></td><td>28.5</td>"
        "<td>2026-09-18 05:51:04</td><td>427.2</td><td>14313288</td>",
    ])
    rows = parse_telemetry_table(html, 1093, "https://panel.htpp.in/graph.php")
    assert len(rows) == 2
    assert rows[0].sampled_at == datetime(2026, 9, 18, 0, 17, 4, tzinfo=timezone.utc)
    assert rows[0].tr_c == 412
    assert rows[0].process_state.value == "heating"
    assert rows[1].pr_bar is None
    assert rows[1].fault_state.value == "choke_emergency"
    assert rows[1].process_state.value == "heating"


def test_temperature_sentinel_is_null():
    html = _html([
        "<td>1</td><td>246</td><td>40</td><td>-1</td><td>-0.01</td><td>0.02</td>"
        "<td>Machine Idle</td><td></td><td></td><td>28.5</td>"
        "<td>2026-09-18 05:47:04</td><td>427.2</td><td>14313288</td>",
        "<td>2</td><td>246</td><td>1479</td><td>1562</td><td>0.01</td><td>0.02</td>"
        "<td>Machine Idle</td><td></td><td></td><td>28.5</td>"
        "<td>2026-09-18 05:51:04</td><td>427.2</td><td>14313288</td>",
    ])
    rows = parse_telemetry_table(html, 1094, "https://panel.htpp.in/graph.php")
    assert rows[0].tr_c is None
    assert rows[1].tr_c is None
    assert rows[1].ts_c is None
    assert rows[0].ps_bar == -0.01


def test_max_sampled_at_reads_timestamptz(tmp_path):
    import duckdb

    from htpp.store.queries import max_sampled_at

    con = duckdb.connect(str(tmp_path / "tz.duckdb"))
    con.execute("CREATE TABLE telemetry_raw (machine_id INTEGER, sampled_at TIMESTAMPTZ)")
    con.execute(
        "INSERT INTO telemetry_raw VALUES (1093, TIMESTAMPTZ '2026-09-19 03:38:00+00')"
    )
    stamp = max_sampled_at(con, 1093)
    con.close()
    assert stamp is not None
    assert stamp.tzinfo is not None
    assert stamp.utcoffset() is not None


def test_refresh_upsert_updates_existing_row(tmp_path, monkeypatch):
    from htpp.config import settings
    from htpp.ingest.seed_fixture import _batch_833
    from htpp.store.db import connect, migrate
    from htpp.store.writes import upsert_telemetry

    monkeypatch.setattr(settings, "db_path", str(tmp_path / "t.duckdb"))
    con = migrate(connect())
    rows = _batch_833()[:1]
    upsert_telemetry(con, rows)
    rows[0].tr_c = 401.0
    rows[0].process_state = rows[0].process_state.__class__("cooling")
    assert upsert_telemetry(con, rows, refresh=True) == 0
    stored = con.execute("SELECT tr_c, process_state FROM telemetry_raw").fetchone()
    con.close()
    assert stored == (401.0, "cooling")


def test_schema_drift():
    with pytest.raises(SchemaDriftError):
        parse_telemetry_table("<table><thead><tr><th>SN</th></tr></thead></table>", 1093, "x")


def test_empty_table():
    html = _html([]) + "No data available in table"
    assert parse_telemetry_table(html, 1093, "x") == []


def test_forbidden_path():
    import asyncio
    async def run():
        client = PanelClient()
        try:
            with pytest.raises(ForbiddenPathError):
                await client.get("/config.php")
            with pytest.raises(ForbiddenPathError):
                await client.get("/logout.php")
        finally:
            await client.aclose()
    asyncio.run(run())


def test_diverging_trajectory_falls_back():
    traj = dense_trajectory(
        tr_c=200, ts_c=40, pr_bar=0.1, ps_bar=0.0, amb_temp_c=28,
        process_state="heating", tau_cool_min=30, q_in_w=1e15, ua_w_per_k=1e-6,
    )
    assert traj.interpolation_mode == "linear_fallback"
    assert len(traj.tr_c) == 301
    assert all(0 <= v <= 900 for v in traj.tr_c)


def test_batch_833_phases():
    from htpp.batches.segment import segment
    from htpp.ingest.seed_fixture import _batch_833

    rows = _batch_833()
    frame = pd.DataFrame([r.model_dump() for r in rows])
    frame["process_state"] = frame["process_state"].astype(str)
    frame["fault_state"] = frame["fault_state"].astype(str)
    batches, phases = segment(frame)
    states = phases["process_state"].tolist()
    assert states[:6] == ["heating", "gas", "cooling", "n2_purging", "carbon_discharge", "main_door_open"]
    expected = {"heating": 103, "gas": 394, "cooling": 256, "n2_purging": 220, "carbon_discharge": 170}
    for row in phases.itertuples(index=False):
        if row.process_state in expected:
            assert abs(row.duration_min - expected[row.process_state]) <= 4


def test_upsert_idempotent(tmp_path, monkeypatch):
    from htpp.config import settings
    from htpp.ingest.seed_fixture import _batch_833
    from htpp.store.db import connect, migrate
    from htpp.store.writes import upsert_telemetry

    monkeypatch.setattr(settings, "db_path", str(tmp_path / "t.duckdb"))
    con = migrate(connect())
    rows = _batch_833()[:5]
    assert upsert_telemetry(con, rows) == 5
    assert upsert_telemetry(con, rows) == 0
    assert con.execute("SELECT COUNT(*) FROM telemetry_raw").fetchone()[0] == 5
    con.close()
