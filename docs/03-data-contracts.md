# 03 - Data Contracts

**This document is the single source of truth for every field name, unit and
dtype in the system.** `backend/src/htpp/schemas.py`, the DuckDB DDL, the API
response models and the frontend TypeScript types must all match it exactly. If
any of them disagrees with this document, the code is wrong.

Naming rules, applied everywhere with no exceptions:

- `snake_case` in Python, SQL and JSON payloads. The frontend converts to
  `camelCase` at the API client boundary only, nowhere else.
- Every physical quantity carries its unit as a suffix: `_c`, `_bar`, `_kg`,
  `_pct`, `_s`, `_min`, `_c_per_min`, `_w_per_k`, `_j_per_k`.
- All timestamps are timezone-aware UTC in storage and transport. Render in
  Asia/Kolkata in the UI only.
- Panel values are stored as given, unconverted. Derived values live in separate
  tables so raw stays auditable.

---

## 1. Panel telemetry, verified against the live panel

Source page: `graph.php?machineid={id}&date=...&date1=...&time=...&time1=...&submit=Submit`

The HTML table on that page has exactly these headers, in this order, confirmed
on 2026-09-19:

```
SN | Batch No | Ts | Tr | Ps | Pr | Process | ROH | ROH Cal. | Amb. Temp. | Date Time | Version | Panel Chip Id
```

### Table `telemetry_raw`

| Column | Type | Unit | Source header | Notes |
|---|---|---|---|---|
| `machine_id` | INTEGER | - | URL param | 1093, 1094 or 1146 |
| `sampled_at` | TIMESTAMPTZ | - | `Date Time` | Panel emits `YYYY-MM-DD HH:MM:SS`, naive, Asia/Kolkata. Localise on parse, store UTC |
| `batch_no` | INTEGER | - | `Batch No` | Panel's own counter. Monotonic per machine, resets are possible, handle them |
| `ts_c` | DOUBLE | degC | `Ts` | Separator temperature |
| `tr_c` | DOUBLE | degC | `Tr` | Reactor temperature. **Primary modelling variable** |
| `ps_bar` | DOUBLE | bar | `Ps` | Separator pressure |
| `pr_bar` | DOUBLE | bar | `Pr` | Reactor pressure. Can be negative, observed -0.01 |
| `process_raw` | VARCHAR | - | `Process` | Verbatim panel string. **Never normalise in place** |
| `roh_c_per_min` | DOUBLE | degC/min | `ROH` | Panel-reported rate of heating |
| `roh_cal_c_per_min` | DOUBLE | degC/min | `ROH Cal.` | Panel's calculated variant. Meaning unconfirmed, ask the plant |
| `amb_temp_c` | DOUBLE | degC | `Amb. Temp.` | Ambient. **Required by the thermal model**, do not drop it |
| `panel_version` | VARCHAR | - | `Version` | e.g. `427.2`. Firmware changes can shift sensor behaviour, keep it |
| `panel_chip_id` | VARCHAR | - | `Panel Chip Id` | e.g. `14313288`. Identifies the physical controller |
| `ingested_at` | TIMESTAMPTZ | - | - | When we fetched it |
| `source_url` | VARCHAR | - | - | Full request URL, for provenance |

**Primary key:** `(machine_id, sampled_at)`

**Parsing rules:**

- Locate columns **by header text, not by index.** The panel may add columns.
  If a required header is missing, fail loudly with the header list it did find.
  Never silently shift.
- `Pr` can render as the literal string `OPEN` on the dashboard tile. If it ever
  appears non-numeric in this table, store `NULL` in `pr_bar` and append
  `pr_non_numeric` to `quality_flags` on the owning batch.
- Empty cells become `NULL`, never `0`. A missing pressure reading is not zero
  pressure and modelling it as zero will corrupt the fit.
- Drop the `SN` column. It is a per-request row counter with no meaning.
- Rows arrive newest first. Sort ascending by `sampled_at` before any modelling.

### Observed cadence and volume

| Window tested | Rows | Implied interval |
|---|---|---|
| 24 hours, machine 1093 | 360 | ~4.0 min |
| 3 days (Sept 15-17), machine 1093 | 995 | ~4.3 min |
| 3 days (Aug 15-17), machine 1093 | 712 | ~6.1 min, gaps present |

Cadence is **not** fixed. Never assume a uniform grid. Every model must work on
irregular timestamps, and every derivative must use actual elapsed time between
samples rather than a constant `dt`.

### History extent, as measured

| Range queried, machine 1093 | Result |
|---|---|
| 2026-06-01 to 06-03 | 0 rows |
| 2026-07-10 to 07-12 | 0 rows |
| 2026-08-01 to 08-03 | 0 rows |
| 2026-08-15 to 08-17 | 712 rows |
| 2026-09-15 to 09-17 | 995 rows |

The history floor sits between 2026-08-03 and 2026-08-15. Treat available history
as roughly five to six weeks and shrinking. Backfill is urgent.

---

## 2. Process state vocabulary

`process_raw` holds the verbatim panel string. Map it to a canonical enum in a
**separate column**, never by overwriting.

### Observed values, confirmed present in real data

From the telemetry table:

```
Machine Idle
Process On
Solenoid On
Cooling On
Carbon Discharge
Choke Emergency
Gas Passage Choke
```

From the dashboard phase timeline (uppercase, different surface, same process):

```
HEATING
GAS
COOLING
N2 PURGING
CARBON DISCHARGE
MAIN DOOR OPEN
```

Also seen as a dashboard status annotation:

```
Pressure Sensor Error
```

### Canonical enum `ProcessState`

```python
class ProcessState(str, Enum):
    IDLE             = "idle"
    HEATING          = "heating"
    GAS              = "gas"
    COOLING          = "cooling"
    N2_PURGING       = "n2_purging"
    CARBON_DISCHARGE = "carbon_discharge"
    MAIN_DOOR_OPEN   = "main_door_open"
    SOLENOID_ON      = "solenoid_on"
    UNKNOWN          = "unknown"
```

### Canonical enum `FaultState`, orthogonal to `ProcessState`

A reactor can be heating **and** choked at the same time. These are separate
dimensions and must not be collapsed into one column.

```python
class FaultState(str, Enum):
    NONE                 = "none"
    CHOKE_EMERGENCY      = "choke_emergency"
    GAS_PASSAGE_CHOKE    = "gas_passage_choke"
    PRESSURE_SENSOR_ERROR = "pressure_sensor_error"
    UNKNOWN_FAULT        = "unknown_fault"
```

### Mapping table

Stored as `backend/src/htpp/ingest/process_map.yaml` so new strings are a config
edit. Matching is case-insensitive on the whitespace-stripped string.

| `process_raw` | `process_state` | `fault_state` |
|---|---|---|
| `Machine Idle` | `idle` | `none` |
| `HEATING` | `heating` | `none` |
| `Process On` | `heating` | `none` |
| `GAS` | `gas` | `none` |
| `Solenoid On` | `solenoid_on` | `none` |
| `COOLING`, `Cooling On` | `cooling` | `none` |
| `N2 PURGING` | `n2_purging` | `none` |
| `CARBON DISCHARGE`, `Carbon Discharge` | `carbon_discharge` | `none` |
| `MAIN DOOR OPEN` | `main_door_open` | `none` |
| `Choke Emergency` | *carry previous* | `choke_emergency` |
| `Gas Passage Choke` | *carry previous* | `gas_passage_choke` |
| `Pressure Sensor Error` | *carry previous* | `pressure_sensor_error` |
| anything else | `unknown` | `unknown_fault` |

**"Carry previous" means:** when the panel reports a fault string, the process
phase it reports is being displaced by the alarm. Forward-fill `process_state`
from the last non-fault sample of the same batch. This matters for the 3D scene:
a choked reactor that was heating must still render as heating, with a choke alarm
layered on top. If it renders as `unknown` the shell glow will drop out mid-batch
and look like a bug.

**`Process On` mapping to `heating` is an assumption.** Verify it by checking
whether `tr_c` is rising while `Process On` is reported. Cursor must add a test
that asserts this and flags it if the correlation fails.

Any `process_raw` value not in the table must be logged at WARNING with machine,
timestamp and the raw string, and surfaced on the `/data` page. New fault strings
are findings, not noise.

---

## 3. Derived tables

### Table `batches`

One row per `(machine_id, batch_no)`.

| Column | Type | Unit | Notes |
|---|---|---|---|
| `batch_key` | VARCHAR | - | `"{machine_id}-{batch_no}"`. Primary key, used in URLs |
| `machine_id` | INTEGER | - | |
| `batch_no` | INTEGER | - | |
| `started_at` | TIMESTAMPTZ | - | First sample of the batch |
| `ended_at` | TIMESTAMPTZ | - | Last sample before the next batch begins |
| `total_duration_min` | DOUBLE | min | `ended_at - started_at` |
| `n_samples` | INTEGER | - | |
| `median_interval_s` | DOUBLE | s | Cadence health indicator |
| `max_gap_s` | DOUBLE | s | Largest hole in the batch |
| `peak_tr_c` | DOUBLE | degC | |
| `peak_ts_c` | DOUBLE | degC | |
| `peak_pr_bar` | DOUBLE | bar | |
| `min_pr_bar` | DOUBLE | bar | |
| `is_complete` | BOOLEAN | - | Has heating through to door open or idle |
| `had_fault` | BOOLEAN | - | Any `fault_state != none` |
| `fault_states` | VARCHAR[] | - | Distinct faults seen |
| `panel_version` | VARCHAR | - | Modal value across the batch |
| `quality_flags` | VARCHAR[] | - | See section 6 |

### Table `phases`

One row per contiguous run of the same `process_state` within a batch.

| Column | Type | Unit | Notes |
|---|---|---|---|
| `batch_key` | VARCHAR | - | FK |
| `phase_index` | INTEGER | - | 0-based, ordered by time |
| `process_state` | VARCHAR | - | Canonical enum value |
| `started_at` | TIMESTAMPTZ | - | |
| `ended_at` | TIMESTAMPTZ | - | |
| `duration_min` | DOUBLE | min | |
| `n_samples` | INTEGER | - | |
| `tr_start_c` | DOUBLE | degC | |
| `tr_end_c` | DOUBLE | degC | |
| `tr_peak_c` | DOUBLE | degC | |
| `mean_amb_temp_c` | DOUBLE | degC | |
| `mean_roh_c_per_min` | DOUBLE | degC/min | |

**Primary key:** `(batch_key, phase_index)`

A phase shorter than two samples cannot support a fit. Mark it
`too_short_to_fit` and exclude it from parameter identification, but keep the row.

Reference durations from a real batch, machine 1093 batch 833, for sanity-checking
the segmenter:

| Phase | Duration | Started |
|---|---|---|
| HEATING | 1 h 43 min | 2026-09-18 05:47:04 |
| GAS | 6 h 34 min | 2026-09-18 07:30:33 |
| COOLING | 4 h 16 min | 2026-09-18 14:04:41 |
| N2 PURGING | 3 h 40 min | 2026-09-18 18:21:01 |
| CARBON DISCHARGE | 2 h 50 min | 2026-09-18 22:01:35 |
| MAIN DOOR OPEN | - | 2026-09-19 00:52:21 |
| **Total** | **26 h 17 min** | |

Write this batch into a test fixture. If the segmenter does not reproduce these
six phases with these durations to within one sample interval, it is broken.

---

## 4. Plant Excel batch log

**The real file has not been supplied yet.** Maddy will provide it. Until then
build against `backend/tests/fixtures/batch_log.xlsx`, generated to this schema.

The parser **must** be driven by `backend/src/htpp/ingest/column_map.yaml` so that
adapting to the real spreadsheet is a config edit. Do not hardcode header strings
in Python.

### Table `batch_log`

| Column | Type | Unit | Required | Notes |
|---|---|---|---|---|
| `machine_id` | INTEGER | - | yes | Join key. Plant may write a machine name, map it |
| `batch_no` | INTEGER | - | yes | Join key. **Must match the panel's batch number** |
| `log_date` | DATE | - | yes | |
| `feed_mass_kg` | DOUBLE | kg | yes | Total charged mass |
| `moisture_pct` | DOUBLE | % | yes | Of the feed, wet basis. Confirm basis with plant |
| `feedstock_type` | VARCHAR | - | yes | e.g. `tyre`, `tyre_plastic_mix` |
| `feedstock_mix_pct` | DOUBLE | % | no | Non-tyre fraction if mixed |
| `oil_mass_kg` | DOUBLE | kg | yes | Recovered pyrolysis oil |
| `carbon_mass_kg` | DOUBLE | kg | yes | Recovered carbon black |
| `steel_mass_kg` | DOUBLE | kg | yes | Recovered steel wire |
| `gas_mass_kg` | DOUBLE | kg | no | Usually flared and unmeasured. Expect NULL |
| `operator` | VARCHAR | - | no | Useful covariate, operators differ |
| `notes` | VARCHAR | - | no | Free text. Mine it for unlogged events |
| `source_file` | VARCHAR | - | yes | Provenance |
| `source_row` | INTEGER | - | yes | Provenance |

**Primary key:** `(machine_id, batch_no)`

### Derived yields, table `batch_yields`

Computed, never read from Excel even if Excel contains percentages. Recompute so
the arithmetic is ours and auditable.

| Column | Formula | Unit |
|---|---|---|
| `oil_yield_pct` | `100 * oil_mass_kg / feed_mass_kg` | % |
| `carbon_yield_pct` | `100 * carbon_mass_kg / feed_mass_kg` | % |
| `steel_yield_pct` | `100 * steel_mass_kg / feed_mass_kg` | % |
| `gas_yield_pct` | `100 * gas_mass_kg / feed_mass_kg` if present else NULL | % |
| `accounted_pct` | sum of the non-null yields above | % |
| `closure_error_pct` | `100 - accounted_pct` | % |
| `dry_feed_mass_kg` | `feed_mass_kg * (1 - moisture_pct/100)` | kg |
| `oil_yield_dry_pct` | `100 * oil_mass_kg / dry_feed_mass_kg` | % |

**Closure handling, and be strict about this:**

- `gas_mass_kg` is usually unmeasured. With gas missing, `closure_error_pct`
  represents gas plus moisture loss plus genuine measurement error, all mixed
  together. Do **not** call it "gas yield by difference" unless moisture is also
  subtracted, and even then flag it as inferred.
- `|closure_error_pct| > 5` with gas present: flag `mass_balance_open`.
- `closure_error_pct < 0` (products exceed feed): flag `mass_balance_impossible`.
  **Exclude from training.** Report how many.
- Report the closure error distribution in the validation report. It is an honest
  characterisation of data quality and reviewers will ask for it.

**Modelling targets are yields in percent, not absolute masses.** Absolute mass
is dominated by feed mass, which would make any model look artificially good.
Predicting yield percent is the real problem. State this in the paper.

### `column_map.yaml` shape

```yaml
sheet: "Batch Log"
header_row: 1
columns:
  machine_id:      ["Machine", "Machine ID", "Reactor"]
  batch_no:        ["Batch", "Batch No", "Batch Number"]
  log_date:        ["Date"]
  feed_mass_kg:    ["Input (kg)", "Feed", "Charge kg"]
  moisture_pct:    ["Moisture %", "Moisture"]
  feedstock_type:  ["Material", "Feedstock"]
  oil_mass_kg:     ["Oil (kg)", "Oil"]
  carbon_mass_kg:  ["Carbon (kg)", "Carbon Black", "CB"]
  steel_mass_kg:   ["Steel (kg)", "Wire", "Steel"]
  gas_mass_kg:     ["Gas (kg)"]
  operator:        ["Operator", "Shift"]
  notes:           ["Remarks", "Notes"]
machine_name_to_id:
  "Plant Operator - 1": 1093
  "Reactor 1": 1093
  "R1": 1093
  # 1094 and 1146 names TBC, get them from the plant
```

Each field lists candidate headers. The parser takes the first that matches
case-insensitively after stripping whitespace. A required field with no match is
a hard failure naming the headers actually present.

**Open question for the plant, resolve before the yield model is trusted:** is
`moisture_pct` measured on the feed as charged, and is `feed_mass_kg` wet or dry?
Getting this backwards puts a systematic bias straight into every yield figure.

---

## 5. Feature table

### Table `batch_features`

One row per `batch_key`. Joins `batches`, `phases`, `batch_yields`. This is the
modelling table. Full formulas in doc 05.

| Column | Type | Unit | Group |
|---|---|---|---|
| `batch_key` | VARCHAR | - | key |
| `machine_id` | INTEGER | - | key, also a grouping variable for CV |
| `started_at` | TIMESTAMPTZ | - | key, drives the time-based split |
| `heating_duration_min` | DOUBLE | min | phase |
| `gas_duration_min` | DOUBLE | min | phase |
| `cooling_duration_min` | DOUBLE | min | phase |
| `n2_purge_duration_min` | DOUBLE | min | phase |
| `carbon_discharge_duration_min` | DOUBLE | min | phase |
| `total_duration_min` | DOUBLE | min | phase |
| `peak_tr_c` | DOUBLE | degC | thermal |
| `mean_roh_heating_c_per_min` | DOUBLE | degC/min | thermal |
| `max_roh_c_per_min` | DOUBLE | degC/min | thermal |
| `time_above_350c_min` | DOUBLE | min | severity |
| `time_above_400c_min` | DOUBLE | min | severity |
| `time_above_450c_min` | DOUBLE | min | severity |
| `severity_index_c_min` | DOUBLE | degC.min | severity, the headline feature |
| `tau_cool_min` | DOUBLE | min | identified |
| `ua_eff_w_per_k` | DOUBLE | W/K | identified |
| `c_eff_j_per_k` | DOUBLE | J/K | identified |
| `q_in_heating_w` | DOUBLE | W | identified, effective not physical |
| `alpha_final` | DOUBLE | - | kinetics, modelled conversion 0 to 1 |
| `max_pr_bar` | DOUBLE | bar | pressure |
| `mean_pr_gas_bar` | DOUBLE | bar | pressure |
| `pr_oscillation_count` | INTEGER | - | pressure, choke precursor candidate |
| `pr_integral_bar_min` | DOUBLE | bar.min | pressure |
| `mean_amb_temp_c` | DOUBLE | degC | ambient |
| `feed_mass_kg` | DOUBLE | kg | from batch_log |
| `moisture_pct` | DOUBLE | % | from batch_log |
| `feedstock_type` | VARCHAR | - | from batch_log, one-hot at fit time |
| `oil_yield_pct` | DOUBLE | % | **target** |
| `carbon_yield_pct` | DOUBLE | % | **target** |
| `steel_yield_pct` | DOUBLE | % | **target** |
| `closure_error_pct` | DOUBLE | % | quality |
| `had_fault` | BOOLEAN | - | quality |
| `quality_flags` | VARCHAR[] | - | quality |
| `usable_for_training` | BOOLEAN | - | computed, see section 6 |

**`usable_for_training` is the only gate the model fitting code may consult.**
Exactly one place decides trainability, so the exclusion count is auditable and
reportable.

---

## 6. Quality flags

Array of strings on `batches` and propagated to `batch_features`.

| Flag | Condition | Excludes from training? |
|---|---|---|
| `incomplete_batch` | No heating phase, or no terminal phase | yes |
| `ingestion_gap` | `max_gap_s > 1800` (30 min) | yes |
| `sparse_sampling` | `median_interval_s > 600` (10 min) | yes |
| `too_few_samples` | `n_samples < 60` | yes |
| `no_excel_log` | No matching `batch_log` row | yes for yield models only |
| `mass_balance_open` | `abs(closure_error_pct) > 5` with gas present | no, but flag in report |
| `mass_balance_impossible` | `closure_error_pct < 0` | yes |
| `had_fault` | Any fault state present | **no**, these are the fault-detection positives |
| `pr_non_numeric` | Non-numeric pressure encountered | no |
| `unknown_process_state` | Any `process_state = unknown` | no, but investigate |
| `panel_version_changed` | Firmware changed mid-batch | no, but flag |
| `batch_no_reset` | `batch_no` decreased from the previous batch | yes |
| `phase_order_anomaly` | Phases out of the expected sequence | no, interesting, investigate |

```
usable_for_training = NOT (
      incomplete_batch OR ingestion_gap OR sparse_sampling
   OR too_few_samples OR mass_balance_impossible OR batch_no_reset
)
```

Note that `had_fault` does **not** exclude a batch. Faulted batches are the entire
point of RQ3 and must be retained. Excluding them would be the single most
damaging mistake available here.

---

## 7. Ingestion metadata

### Table `ingest_runs`

| Column | Type | Notes |
|---|---|---|
| `run_id` | VARCHAR | uuid |
| `kind` | VARCHAR | `backfill`, `incremental`, `excel` |
| `machine_id` | INTEGER | NULL for excel |
| `range_start` | TIMESTAMPTZ | |
| `range_end` | TIMESTAMPTZ | |
| `rows_fetched` | INTEGER | |
| `rows_inserted` | INTEGER | New rows only |
| `http_status` | INTEGER | |
| `error` | VARCHAR | NULL on success |
| `duration_s` | DOUBLE | |
| `started_at` | TIMESTAMPTZ | |

Backs the coverage report and the `/data` page. Without it there is no way to
distinguish "the reactor was off" from "we failed to fetch", and those two look
identical in the telemetry table.
