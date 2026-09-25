# 06 - API Spec

FastAPI. All responses are pydantic models so OpenAPI is accurate and the frontend
generates its types from it. Field names are `snake_case` and match doc 03 exactly.

Base path `/api`. WebSocket at `/ws/live`.

**Relationship to doc 03.** Any field that corresponds to a stored column uses that
column's exact name, type and unit from doc 03. Responses additionally carry
**transport-only derived fields** that have no stored column and are defined here
instead: `staleness_s`, `batch_elapsed_min`, `phase_elapsed_min`,
`predicted_total_duration_min`, `r_t_c`, `r_p_bar`, `tr_rmse_c`, `tr_mae_c`,
`total_duration_error_min`, `phase_duration_errors_min`, `yield_errors_pct`,
`start_s`, `end_s`. These are computed at request time. Do not create tables for
them, and do not invent further ones without adding them to this list.

Global rules:

- Every numeric field name carries its unit suffix. No bare `temperature`.
- Timestamps are ISO 8601 with offset, always UTC.
- `null` means unmeasured. It never means zero.
- Errors use a consistent envelope: `{"error": {"code": str, "message": str, "detail": any}}`.
- No endpoint fits a model. Fitting is `make fit`, offline.
- Read-only except `POST /api/ingest/excel` and `POST /api/simulate`.

---

## 1. Metadata

### `GET /api/machines`

```json
[
  {
    "machine_id": 1093,
    "display_name": "Plant Operator - 1",
    "panel_chip_id": "14313288",
    "panel_version": "427.2",
    "history_floor": "2026-08-11T00:00:00Z",
    "last_sample_at": "2026-09-19T02:33:30Z",
    "n_samples": 13704,
    "n_batches": 38,
    "n_batches_complete": 34,
    "has_fitted_model": true,
    "scene_slot": 0
  }
]
```

`scene_slot` fixes each reactor's position in the 3D scene so the layout is stable
across reloads. `display_name` for 1094 and 1146 comes from machine-name discovery
(doc 04 section 6).

### `GET /api/health`

```json
{
  "status": "ok",
  "db_reachable": true,
  "panel_reachable": true,
  "last_ingest_at": "2026-09-19T02:36:00Z",
  "last_ingest_status": "ok",
  "consecutive_ingest_failures": 0,
  "model_version": "20260919T0130Z_a3f9c21",
  "interpolation_mode": "model"
}
```

---

## 2. Telemetry and batches

### `GET /api/machines/{machine_id}/telemetry`

Query: `from` (ISO), `to` (ISO), `downsample` (int, optional target point count).

```json
{
  "machine_id": 1093,
  "from": "2026-09-18T00:00:00Z",
  "to": "2026-09-19T00:00:00Z",
  "n_points": 360,
  "downsampled": false,
  "samples": [
    {
      "sampled_at": "2026-09-18T00:17:04Z",
      "batch_no": 833,
      "ts_c": 193.0,
      "tr_c": 412.0,
      "ps_bar": 0.0,
      "pr_bar": 0.12,
      "amb_temp_c": 28.5,
      "roh_c_per_min": 1.4,
      "process_state": "heating",
      "process_raw": "HEATING",
      "fault_state": "none"
    }
  ]
}
```

When `downsample` is set, use **largest-triangle-three-buckets**, not naive
stride sampling. LTTB preserves peaks, and peaks are exactly what matters in a
temperature trace. Naive striding will hide the spike that caused the choke.

### `GET /api/batches`

Query: `machine_id` (optional), `from`, `to`, `had_fault` (bool), `usable_only`
(bool), `limit`, `offset`.

```json
{
  "total": 112,
  "limit": 50,
  "offset": 0,
  "batches": [
    {
      "batch_key": "1093-833",
      "machine_id": 1093,
      "batch_no": 833,
      "started_at": "2026-09-18T00:17:04Z",
      "ended_at": "2026-09-19T02:34:50Z",
      "total_duration_min": 1577.0,
      "peak_tr_c": 468.0,
      "is_complete": true,
      "had_fault": false,
      "fault_states": [],
      "has_excel_log": true,
      "oil_yield_pct": 42.3,
      "carbon_yield_pct": 31.1,
      "steel_yield_pct": 12.4,
      "closure_error_pct": 14.2,
      "usable_for_training": true,
      "quality_flags": []
    }
  ]
}
```

### `GET /api/batches/{batch_key}`

Everything about one batch: samples, phases, features, yields, model fits,
residual series, detector events.

```json
{
  "batch_key": "1093-833",
  "machine_id": 1093,
  "batch_no": 833,
  "started_at": "2026-09-18T00:17:04Z",
  "ended_at": "2026-09-19T02:34:50Z",
  "total_duration_min": 1577.0,
  "phases": [
    {
      "phase_index": 0,
      "process_state": "heating",
      "started_at": "2026-09-18T00:17:04Z",
      "ended_at": "2026-09-18T02:00:33Z",
      "duration_min": 103.0,
      "tr_start_c": 34.0,
      "tr_end_c": 398.0,
      "tr_peak_c": 398.0,
      "mean_roh_c_per_min": 3.53
    }
  ],
  "features": { "severity_index_c_min": 182400.0, "tau_cool_min": 214.7, "...": null },
  "yields": {
    "measured":  { "oil_yield_pct": 42.3, "carbon_yield_pct": 31.1, "steel_yield_pct": 12.4 },
    "predicted": {
      "oil_yield_pct":    { "p10": 38.1, "p50": 41.7, "p90": 45.4 },
      "carbon_yield_pct": { "p10": 28.8, "p50": 31.6, "p90": 34.2 },
      "steel_yield_pct":  { "p10": 11.2, "p50": 12.6, "p90": 14.0 }
    },
    "in_training_split": false
  },
  "model_fits": {
    "tau_cool_min": 214.7,
    "cooling_r_squared": 0.987,
    "cooling_converged": true,
    "q_in_heating_w": 41200.0,
    "ua_eff_w_per_k": 88.3,
    "c_eff_j_per_k": 1138000.0,
    "alpha_final": 0.91,
    "e_rxn_j": 1.84e9
  },
  "residuals": [
    { "sampled_at": "2026-09-18T02:04:37Z", "r_t_c": 3.1, "r_t_norm": 0.42,
      "r_p_bar": 0.01, "ewma_z": 0.31, "cusum": 0.0, "alarm": false }
  ],
  "detector_events": [],
  "panel_alarm_events": [],
  "samples": [ "... as in the telemetry endpoint ..." ],
  "quality_flags": []
}
```

`in_training_split` must be present on every batch that shows predictions. A
prediction for a training batch is not evidence of anything, and the UI must be
able to label it as such.

### `GET /api/batches/{batch_key}/replay`

Dense simulated trajectory aligned to the measured one, for the 3D replay and the
key paper figure.

```json
{
  "batch_key": "1093-833",
  "in_training_split": false,
  "step_s": 60,
  "t_offset_s":   [0, 60, 120],
  "measured":  { "tr_c": [34.0, null, 41.0], "ts_c": [26.0, null, 28.0],
                 "pr_bar": [0.0, null, 0.0], "ps_bar": [0.0, null, 0.0] },
  "simulated": { "tr_c": [34.0, 37.4, 40.9], "ts_c": [26.0, 27.0, 28.1],
                 "pr_bar": [0.0, 0.0, 0.0],  "ps_bar": [0.0, 0.0, 0.0] },
  "process_state_measured":  ["heating", "heating", "heating"],
  "process_state_simulated": ["heating", "heating", "heating"],
  "fault_state_measured":    ["none", "none", "none"],
  "errors": {
    "tr_rmse_c": 11.4,
    "tr_mae_c": 8.2,
    "total_duration_error_min": -37.0,
    "phase_duration_errors_min": { "heating": -4.0, "gas": -22.0, "cooling": 11.0 },
    "yield_errors_pct": { "oil": -0.6, "carbon": 0.5, "steel": 0.2 }
  }
}
```

`measured` arrays are `null` where no real sample exists at that offset. Do **not**
forward-fill measured data into the simulated grid. The frontend must be able to
draw measured as discrete points and simulated as a continuous line, because that
visual distinction is the honest representation of a 4-minute-cadence dataset.

---

## 3. Live channel

### `WebSocket /ws/live`

The 3D scene's data source. Server pushes; the client sends only `{"type":"ping"}`
for keepalive.

**On connect**, a `snapshot` for every machine so the scene can render immediately
without waiting up to four minutes for the first tick:

```json
{
  "type": "snapshot",
  "server_time": "2026-09-19T02:36:12Z",
  "model_version": "20260919T0130Z_a3f9c21",
  "machines": [
    {
      "machine_id": 1093,
      "scene_slot": 0,
      "online": true,
      "last_sample_at": "2026-09-19T02:33:30Z",
      "staleness_s": 162,
      "batch_no": 833,
      "batch_elapsed_min": 1577.0,
      "process_state": "main_door_open",
      "process_raw": "MAIN DOOR OPEN",
      "fault_state": "none",
      "phase_elapsed_min": 104.0,
      "measured": { "tr_c": 34.0, "ts_c": 26.0, "pr_bar": -0.01, "ps_bar": 0.0,
                    "amb_temp_c": 28.5, "roh_c_per_min": 0.0 },
      "interpolation_mode": "model",
      "dense": {
        "step_s": 1.0,
        "horizon_s": 300,
        "tr_c":    [34.0, 34.0, 33.9],
        "ts_c":    [26.0, 26.0, 26.0],
        "pr_bar":  [-0.01, -0.01, -0.01],
        "ps_bar":  [0.0, 0.0, 0.0],
        "process_state": ["main_door_open", "main_door_open", "main_door_open"]
      },
      "residual": { "r_t_c": 0.4, "r_t_norm": 0.05, "ewma_z": 0.08,
                    "cusum": 0.0, "alarm": false, "severity": "ok" },
      "projection": {
        "predicted_end_at": "2026-09-19T03:10:00Z",
        "predicted_total_duration_min": 1611.0,
        "predicted_yields": {
          "oil_yield_pct":    { "p10": 38.1, "p50": 41.7, "p90": 45.4 },
          "carbon_yield_pct": { "p10": 28.8, "p50": 31.6, "p90": 34.2 },
          "steel_yield_pct":  { "p10": 11.2, "p50": 12.6, "p90": 14.0 }
        }
      }
    }
  ]
}
```

**On each ingestion tick**, a `tick` with the same per-machine shape, for changed
machines only.

```json
{ "type": "tick", "server_time": "...", "machines": [ "... same shape ..." ] }
```

**On a detector or panel alarm**, pushed immediately without waiting for the tick:

```json
{
  "type": "alarm",
  "machine_id": 1094,
  "kind": "detector",
  "fault_state": "gas_passage_choke",
  "severity": "critical",
  "detected_at": "2026-09-19T02:40:00Z",
  "message": "Pressure residual exceeded threshold, CUSUM 4.2",
  "lead_time_min": null
}
```

`kind` is `detector` or `panel`. `severity` is `ok`, `warning` or `critical` and
maps directly to the 3D alarm visuals in doc 08. `lead_time_min` is filled on a
`panel` alarm when a matching detector alarm preceded it, which is the live
demonstration of RQ3 and worth surfacing in the UI.

### Field notes, important for the scene

- **`staleness_s` drives a degraded visual.** If it exceeds about 600 s the panel
  has stopped reporting, and the scene must show that machine as stale rather than
  quietly continuing to animate a projection into the void. A confidently animating
  reactor with dead telemetry is the worst possible failure mode for an operator
  display.
- **`interpolation_mode`** is `model` or `linear_fallback`. The HUD must show which.
- **`dense.process_state`** lets the scene animate a phase transition at the right
  moment inside the interval rather than snapping on the next tick.
- Arrays are 300 floats each at `step_s = 1.0`. Round to one decimal in JSON to
  keep the payload small. Roughly 12 KB per tick for three machines.

### Reconnection

Client reconnects with exponential backoff (1 s, 2 s, 4 s, capped at 30 s) and
receives a fresh `snapshot`. The server must not attempt to replay missed ticks;
the snapshot is authoritative.

---

## 4. Simulation

### `POST /api/simulate`

```json
{
  "machine_id": 1093,
  "feed_mass_kg": 8000,
  "moisture_pct": 2.5,
  "feedstock_type": "tyre",
  "target_peak_tr_c": 460,
  "heating_power_scale": 1.0,
  "amb_temp_c": 28.5,
  "step_s": 60
}
```

Response:

```json
{
  "input_echo": { "...": null },
  "model_version": "20260919T0130Z_a3f9c21",
  "t_offset_s": [0, 60, 120],
  "tr_c": [30.0, 34.1, 38.3],
  "ts_c": [28.5, 28.9, 29.6],
  "pr_bar": [0.0, 0.0, 0.0],
  "ps_bar": [0.0, 0.0, 0.0],
  "process_state": ["heating", "heating", "heating"],
  "phases": [
    { "process_state": "heating", "start_s": 0, "end_s": 6180, "duration_min": 103.0 }
  ],
  "predicted_total_duration_min": 1577.0,
  "predicted_yields": {
    "oil_yield_pct":    { "p10": 38.1, "p50": 41.7, "p90": 45.4 },
    "carbon_yield_pct": { "p10": 28.8, "p50": 31.6, "p90": 34.2 },
    "steel_yield_pct":  { "p10": 11.2, "p50": 12.6, "p90": 14.0 }
  },
  "extrapolation_warnings": [
    "feed_mass_kg 8000 is above the training range maximum of 7200"
  ]
}
```

**`extrapolation_warnings` is mandatory and must be surfaced prominently in the UI.**
Compare every input against the training-data range and warn on anything outside
it. With about 100 training batches, a model asked to extrapolate will produce a
confident and meaningless number, and an operator has no way to know. This warning
is the difference between a useful tool and a dangerous one.

### `GET /api/models/metrics`

Serves `metrics.json` from the loaded artefact directory verbatim: every held-out
metric, every baseline, the split manifest summary, feature importances, coverage
of prediction intervals, fault-detection precision, recall and lead-time
distribution. The `/model` page renders this, and the paper tables come from the
same file.

---

## 5. Data quality

### `GET /api/data/coverage`

Backs the `/data` page and the paper's data-section figure.

```json
{
  "per_machine": [
    {
      "machine_id": 1093,
      "history_floor": "2026-08-11T00:00:00Z",
      "last_sample_at": "2026-09-19T02:33:30Z",
      "n_samples": 13704,
      "median_interval_s": 243.0,
      "daily": [ { "date": "2026-09-18", "n_samples": 358, "median_interval_s": 241.0,
                   "max_gap_s": 420 } ],
      "gaps": [ { "from": "2026-08-22T11:04:00Z", "to": "2026-08-22T19:31:00Z",
                  "duration_s": 30420 } ]
    }
  ],
  "batches": { "total": 112, "complete": 98, "usable_for_training": 91,
               "with_excel_log": 88, "with_fault": 14 },
  "excel": {
    "rows_parsed": 94,
    "rows_unmatched": 6,
    "unmatched_detail": [ { "machine_id": 1146, "batch_no": 412,
                            "reason": "no panel batch with this number" } ],
    "closure_error_pct": { "median": 13.8, "p10": 8.1, "p90": 22.4,
                           "n_impossible": 2 }
  },
  "unmapped_process_values": [],
  "ingest_failures": []
}
```

### `POST /api/ingest/excel`

Multipart upload of a batch-log `.xlsx`. Parses through `column_map.yaml`, upserts,
returns rows parsed, rows inserted, rows updated, and a per-row error list.

**Never partially commit.** Parse the entire file, and if any required field fails
to map, reject the whole upload and return the list of headers found alongside the
list expected. A half-imported batch log is much harder to detect and repair than a
rejected upload.

---

## 6. What the API must never do

- Fit or refit a model on request. Load artefacts only.
- Return a prediction without indicating whether the batch was in the training split.
- Return a simulated value outside the training range without a warning.
- Forward-fill measured telemetry so it looks denser than it is.
- Expose panel credentials or the session cookie in any response, including errors.
- Proxy arbitrary requests to the panel. There is no `GET /api/panel/{path}`
  passthrough, because it would defeat the read-only allowlist in doc 04.
