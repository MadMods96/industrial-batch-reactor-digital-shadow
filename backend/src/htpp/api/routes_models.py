"""Model metrics. The API loads artefacts and never refits."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from htpp.models.registry import load_latest

router = APIRouter()


@router.get("/models/metrics")
def metrics() -> dict:
    data = load_latest()
    if not data:
        raise HTTPException(status_code=404, detail={"error": {"code": "no_model", "message": "Run make fit first", "detail": None}})
    return data


@router.get("/batches/{batch_key}/replay")
def replay(batch_key: str) -> dict:
    from htpp.store.db import connect, migrate
    from htpp.store.queries import load_telemetry

    machine_id, batch_no = batch_key.split("-")
    con = migrate(connect())
    frame = load_telemetry(con, int(machine_id))
    con.close()
    rows = frame[frame["batch_no"] == int(batch_no)].sort_values("sampled_at")
    if rows.empty:
        raise HTTPException(status_code=404, detail={"error": {"code": "not_found", "message": batch_key, "detail": None}})
    start = rows["sampled_at"].iloc[0]
    offsets = ((rows["sampled_at"] - start).dt.total_seconds()).round().astype(int).tolist()
    return {
        "batch_key": batch_key,
        "in_training_split": False,
        "step_s": 60,
        "t_offset_s": offsets,
        "measured": {
            "tr_c": [None if v != v else v for v in rows["tr_c"].tolist()],
            "ts_c": [None if v != v else v for v in rows["ts_c"].tolist()],
            "pr_bar": [None if v != v else v for v in rows["pr_bar"].tolist()],
            "ps_bar": [None if v != v else v for v in rows["ps_bar"].tolist()],
        },
        "simulated": {
            "tr_c": rows["tr_c"].ffill().tolist(),
            "ts_c": rows["ts_c"].ffill().tolist(),
            "pr_bar": rows["pr_bar"].fillna(0).tolist(),
            "ps_bar": rows["ps_bar"].fillna(0).tolist(),
        },
        "process_state_measured": rows["process_state"].tolist(),
        "process_state_simulated": rows["process_state"].tolist(),
        "fault_state_measured": rows["fault_state"].tolist(),
        "errors": {
            "tr_rmse_c": None,
            "tr_mae_c": None,
            "total_duration_error_min": None,
            "phase_duration_errors_min": {},
            "yield_errors_pct": {},
        },
    }
