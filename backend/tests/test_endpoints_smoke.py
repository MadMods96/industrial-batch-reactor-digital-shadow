"""Every doc-06 endpoint against the real database. No synthetic excel is committed."""

from __future__ import annotations

from fastapi.testclient import TestClient
from openpyxl import Workbook
from pydantic import TypeAdapter

from htpp.schemas import HealthResponse, MachineSummary

ORIGIN = "http://localhost:3000"


def _client() -> TestClient:
    from htpp.api.main import create_app

    app = create_app()

    @app.get("/api/_boom")
    def boom() -> dict:
        raise RuntimeError("forced")

    return TestClient(app, raise_server_exceptions=False)


def test_doc06_endpoints_against_real_db(tmp_path):
    with _client() as client:
        health = client.get("/api/health")
        assert health.status_code == 200, health.text
        HealthResponse.model_validate(health.json())
        assert health.json()["status"] == "ok"
        assert health.json()["db_reachable"] is True

        machines = client.get("/api/machines")
        assert machines.status_code == 200, machines.text
        summaries = TypeAdapter(list[MachineSummary]).validate_python(machines.json())
        assert summaries
        machine_id = summaries[0].machine_id

        telemetry = client.get(f"/api/machines/{machine_id}/telemetry", params={"downsample": 20})
        assert telemetry.status_code == 200, telemetry.text
        body = telemetry.json()
        assert body["machine_id"] == machine_id
        assert "samples" in body

        listing = client.get("/api/batches", params={"limit": 5})
        assert listing.status_code == 200, listing.text
        listed = listing.json()
        assert listed["total"] >= 1
        assert listed["batches"]
        batch_key = listed["batches"][0]["batch_key"]
        for row in listed["batches"]:
            assert "quality_flags" in row
            assert "usable_for_training" in row

        detail = client.get("/api/batches/1093-833")
        assert detail.status_code == 200, detail.text
        one = detail.json()
        assert isinstance(one["phases"], list) and one["phases"]
        assert isinstance(one["features"], dict) and one["features"]
        assert "model_fits" in one

        replay = client.get(f"/api/batches/{batch_key}/replay")
        assert replay.status_code == 200, replay.text
        assert replay.json()["batch_key"] == batch_key

        metrics = client.get("/api/models/metrics")
        assert metrics.status_code == 200, metrics.text
        assert "model_version" in metrics.json() or "interpolation_mode" in metrics.json()

        coverage = client.get("/api/data/coverage")
        assert coverage.status_code == 200, coverage.text
        cov = coverage.json()
        usable_rows = client.get("/api/batches", params={"usable_only": True, "limit": 500}).json()
        assert cov["batches"]["usable_for_training"] == usable_rows["total"]
        for machine in cov["per_machine"]:
            if machine["n_samples"] > 1:
                assert machine["median_interval_s"] is not None

        simulated = client.post("/api/simulate", json={
            "machine_id": 1093,
            "feed_mass_kg": 8000,
            "moisture_pct": 2.5,
            "feedstock_type": "tyre",
            "target_peak_tr_c": 460,
            "heating_power_scale": 1.0,
            "amb_temp_c": 28.5,
            "step_s": 60,
        })
        assert simulated.status_code == 200, simulated.text
        assert "tr_c" in simulated.json()

        book = Workbook()
        book.active.append(["not", "a", "log"])
        path = tmp_path / "smoke-reject.xlsx"
        book.save(path)
        rejected = client.post(
            "/api/ingest/excel",
            files={"file": ("smoke-reject.xlsx", path.read_bytes(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
        assert rejected.status_code == 422, rejected.text
        assert "error" in rejected.json().get("detail", rejected.json())

        boom = client.get("/api/_boom", headers={"Origin": ORIGIN})
        assert boom.status_code == 500, boom.text
        envelope = boom.json()["error"]
        assert envelope["code"] and envelope["message"] and envelope["detail"]
        assert boom.headers["access-control-allow-origin"] == ORIGIN

        with client.websocket_connect("/ws/live") as ws:
            snap = ws.receive_json()
        assert snap["type"] == "snapshot"
