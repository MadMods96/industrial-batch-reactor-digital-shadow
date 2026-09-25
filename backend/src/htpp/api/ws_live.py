"""Live channel. A snapshot is sent on connect; missed ticks are not replayed."""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone

import pandas as pd
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from htpp.models.registry import load_latest, project_machine
from htpp.plant import machine_label
from htpp.store.db import connect, migrate
from htpp.store.queries import latest_per_machine, load_batches

router = APIRouter()
_clients: set[WebSocket] = set()
SLOTS = {1093: 0, 1094: 1, 1146: 2}

@router.websocket("/ws/live")
async def live(ws: WebSocket) -> None:
    await ws.accept()
    _clients.add(ws)
    try:
        await ws.send_text(_dumps(_snapshot()))
        while True:
            message = await ws.receive_text()
            if message:
                payload = json.loads(message)
                if payload.get("type") == "ping":
                    await ws.send_text(
                        _dumps({"type": "pong", "server_time": datetime.now(timezone.utc).isoformat()})
                    )
    except WebSocketDisconnect:
        _clients.discard(ws)
    except Exception:
        _clients.discard(ws)


async def broadcast_tick() -> None:
    payload = _snapshot()
    payload["type"] = "tick"
    text = _dumps(payload)
    dead = []
    for client in list(_clients):
        try:
            await client.send_text(text)
        except Exception:
            dead.append(client)
    for client in dead:
        _clients.discard(client)


def _dumps(payload: dict) -> str:
    return json.dumps(payload, allow_nan=False, default=str)


def _snapshot() -> dict:
    con = migrate(connect())
    latest = latest_per_machine(con)
    batches = load_batches(con)
    con.close()
    model = load_latest()
    machines = []
    now = datetime.now(timezone.utc)
    if not latest.empty:
        for row in latest.to_dict("records"):
            machines.append(_machine(row, batches, now))
    return {
        "type": "snapshot",
        "server_time": now.isoformat(),
        "model_version": model.get("model_version"),
        "machines": machines,
    }


def _machine(row: dict, batches: pd.DataFrame, now: datetime) -> dict:
    machine_id = int(row["machine_id"])
    sampled = pd.Timestamp(row["sampled_at"])
    if sampled.tzinfo is None:
        sampled = sampled.tz_localize("UTC")
    staleness = (pd.Timestamp(now) - sampled).total_seconds()
    batch_no = None if pd.isna(row["batch_no"]) else int(row["batch_no"])
    elapsed = None
    phase_elapsed = None
    if not batches.empty and batch_no is not None:
        match = batches[(batches["machine_id"] == machine_id) & (batches["batch_no"] == batch_no)]
        if not match.empty:
            started = pd.Timestamp(match.iloc[0]["started_at"])
            if started.tzinfo is None:
                started = started.tz_localize("UTC")
            elapsed = (sampled - started).total_seconds() / 60.0
            phase_elapsed = elapsed
    projection = project_machine(pd.Series(row))
    return {
        "machine_id": machine_id,
        "display_name": machine_label(machine_id),
        "scene_slot": SLOTS.get(machine_id, 0),
        "online": staleness < 3600,
        "last_sample_at": sampled.isoformat(),
        "staleness_s": _f(staleness),
        "batch_no": batch_no,
        "batch_elapsed_min": _f(elapsed),
        "process_state": row.get("process_state") or "unknown",
        "process_raw": row.get("process_raw"),
        "fault_state": row.get("fault_state") or "none",
        "phase_elapsed_min": _f(phase_elapsed),
        "measured": {
            "tr_c": _f(row.get("tr_c")),
            "ts_c": _f(row.get("ts_c")),
            "pr_bar": _f(row.get("pr_bar")),
            "ps_bar": _f(row.get("ps_bar")),
            "amb_temp_c": _f(row.get("amb_temp_c")),
            "roh_c_per_min": _f(row.get("roh_c_per_min")),
        },
        "interpolation_mode": projection["interpolation_mode"],
        "dense": projection["dense"],
        "residual": {
            "r_t_c": 0.0,
            "r_t_norm": 0.0,
            "r_p_bar": 0.0,
            "ewma_z": 0.0,
            "cusum": 0.0,
            "alarm": False,
            "severity": "ok",
        },
        "projection": {
            "predicted_end_at": None,
            "predicted_total_duration_min": None,
            "predicted_yields": None,
        },
    }


def _f(value):
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    try:
        number = float(value)
    except (TypeError, ValueError):
        return value
    if math.isnan(number) or math.isinf(number):
        return None
    return number
