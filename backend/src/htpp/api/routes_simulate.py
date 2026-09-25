"""What-if simulation. Out-of-range inputs always return extrapolation warnings."""

from __future__ import annotations

from fastapi import APIRouter

from htpp.models.registry import load_latest, machine_params
from htpp.models.simulate import simulate_batch
from htpp.schemas import SimulateRequest

router = APIRouter()


@router.post("/simulate")
def simulate(body: SimulateRequest) -> dict:
    params = machine_params(body.machine_id)
    model = load_latest()
    ua = params.get("ua_eff_w_per_k") or 80.0
    c_shell = params.get("c_shell_j_per_k") or 800_000.0
    q_h = params.get("q_h_w") or 40_000.0
    result = simulate_batch(
        feed_mass_kg=body.feed_mass_kg,
        moisture_pct=body.moisture_pct,
        feedstock_type=body.feedstock_type,
        target_peak_tr_c=body.target_peak_tr_c,
        heating_power_scale=body.heating_power_scale,
        amb_temp_c=body.amb_temp_c,
        ua_w_per_k=ua,
        c_shell_j_per_k=c_shell,
        q_h_w=q_h,
        step_s=body.step_s,
        train_ranges=model.get("train_ranges") or {"feed_mass_kg": [4500, 6500], "moisture_pct": [1.0, 4.0], "target_peak_tr_c": [420, 480]},
    )
    if not params:
        result["extrapolation_warnings"] = [
            "No fitted model for this machine yet. Trajectory uses nominal parameters and is not a prediction.",
            *result["extrapolation_warnings"],
        ]
    return {
        "input_echo": body.model_dump(),
        "model_version": model.get("model_version"),
        **result,
    }
