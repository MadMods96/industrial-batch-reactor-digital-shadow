"""Pydantic models mirroring docs/03-data-contracts.md and docs/06-api-spec.md."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class ProcessState(str, Enum):
    IDLE = "idle"
    HEATING = "heating"
    GAS = "gas"
    COOLING = "cooling"
    N2_PURGING = "n2_purging"
    CARBON_DISCHARGE = "carbon_discharge"
    MAIN_DOOR_OPEN = "main_door_open"
    SOLENOID_ON = "solenoid_on"
    UNKNOWN = "unknown"


class FaultState(str, Enum):
    NONE = "none"
    CHOKE_EMERGENCY = "choke_emergency"
    GAS_PASSAGE_CHOKE = "gas_passage_choke"
    PRESSURE_SENSOR_ERROR = "pressure_sensor_error"
    UNKNOWN_FAULT = "unknown_fault"


class TelemetrySample(BaseModel):
    machine_id: int
    sampled_at: datetime
    batch_no: int | None = None
    ts_c: float | None = None
    tr_c: float | None = None
    ps_bar: float | None = None
    pr_bar: float | None = None
    process_raw: str | None = None
    process_state: ProcessState = ProcessState.UNKNOWN
    fault_state: FaultState = FaultState.NONE
    roh_c_per_min: float | None = None
    roh_cal_c_per_min: float | None = None
    amb_temp_c: float | None = None
    panel_version: str | None = None
    panel_chip_id: str | None = None
    ingested_at: datetime | None = None
    source_url: str | None = None


class BatchLogEntry(BaseModel):
    machine_id: int
    batch_no: int
    log_date: datetime | None = None
    feed_mass_kg: float
    moisture_pct: float
    feedstock_type: str
    feedstock_mix_pct: float | None = None
    oil_mass_kg: float
    carbon_mass_kg: float
    steel_mass_kg: float
    gas_mass_kg: float | None = None
    operator: str | None = None
    notes: str | None = None
    source_file: str
    source_row: int


class Interval(BaseModel):
    p10: float | None = None
    p50: float | None = None
    p90: float | None = None


class YieldIntervals(BaseModel):
    oil_yield_pct: Interval
    carbon_yield_pct: Interval
    steel_yield_pct: Interval


class MeasuredBlock(BaseModel):
    tr_c: float | None = None
    ts_c: float | None = None
    pr_bar: float | None = None
    ps_bar: float | None = None
    amb_temp_c: float | None = None
    roh_c_per_min: float | None = None


class ResidualBlock(BaseModel):
    r_t_c: float | None = None
    r_t_norm: float | None = None
    r_p_bar: float | None = None
    ewma_z: float | None = None
    cusum: float | None = None
    alarm: bool = False
    severity: str = "ok"


class DenseBlock(BaseModel):
    step_s: float = 1.0
    horizon_s: float = 300.0
    tr_c: list[float]
    ts_c: list[float]
    pr_bar: list[float]
    ps_bar: list[float]
    process_state: list[str]


class ProjectionBlock(BaseModel):
    predicted_end_at: datetime | None = None
    predicted_total_duration_min: float | None = None
    predicted_yields: YieldIntervals | None = None


class MachineLive(BaseModel):
    machine_id: int
    scene_slot: int
    online: bool
    last_sample_at: datetime | None = None
    staleness_s: float | None = None
    batch_no: int | None = None
    batch_elapsed_min: float | None = None
    process_state: str = "unknown"
    process_raw: str | None = None
    fault_state: str = "none"
    phase_elapsed_min: float | None = None
    measured: MeasuredBlock
    interpolation_mode: str = "linear_fallback"
    dense: DenseBlock
    residual: ResidualBlock
    projection: ProjectionBlock


class LiveMessage(BaseModel):
    type: str
    server_time: datetime
    model_version: str | None = None
    machines: list[MachineLive] = Field(default_factory=list)


class AlarmMessage(BaseModel):
    type: str = "alarm"
    machine_id: int
    kind: str
    fault_state: str
    severity: str
    detected_at: datetime
    message: str
    lead_time_min: float | None = None


class MachineSummary(BaseModel):
    machine_id: int
    display_name: str
    panel_chip_id: str | None = None
    panel_version: str | None = None
    history_floor: datetime | None = None
    last_sample_at: datetime | None = None
    n_samples: int = 0
    n_batches: int = 0
    n_batches_complete: int = 0
    has_fitted_model: bool = False
    scene_slot: int = 0


class HealthResponse(BaseModel):
    status: str
    db_reachable: bool
    panel_reachable: bool | None = None
    last_ingest_at: datetime | None = None
    last_ingest_status: str | None = None
    consecutive_ingest_failures: int = 0
    model_version: str | None = None
    interpolation_mode: str = "linear_fallback"


class ErrorBody(BaseModel):
    code: str
    message: str
    detail: object | None = None


class ErrorEnvelope(BaseModel):
    error: ErrorBody


class SimulateRequest(BaseModel):
    machine_id: int
    feed_mass_kg: float
    moisture_pct: float
    feedstock_type: str = "tyre"
    target_peak_tr_c: float = 460.0
    heating_power_scale: float = 1.0
    amb_temp_c: float = 28.5
    step_s: float = 60.0
