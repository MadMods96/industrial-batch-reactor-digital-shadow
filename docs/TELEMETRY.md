# Panel & Excel data formats

This document describes **only** the data shapes the shadow consumes. Site and customer names are configured in `.env`, not here.

---

## 1. Live / historical panel samples

Approximate cadence: **one row per machine every ~4 minutes**.

| Column | Type | Unit | What it is |
|--------|------|------|------------|
| `machine_id` | integer | — | Reactor identity from the panel |
| `sampled_at` | ISO-8601 datetime | UTC in DB | When the sample was taken |
| `tr_c` | float | °C | Temperature inside the reactor |
| `ts_c` | float | °C | Temperature at the separator |
| `pr_bar` | float | bar | Pressure in the reactor |
| `ps_bar` | float | bar | Pressure at the separator |
| `roh_c_per_min` | float | °C/min | Rate of heating reported by the panel |
| `amb_temp_c` | float | °C | Ambient / room temperature |
| `process_raw` | string | — | Human process label from the panel UI |
| `process_state` | string | — | Normalized state used by the model and 3D scene |
| `fault_raw` | string / null | — | Fault text when the panel shows a fault |
| `fault_state` | string | — | Normalized fault code (`none`, choke, sensor error, …) |
| `batch_no` | integer / null | — | Batch number when the panel associates one |

### Normalized process states (examples)

| `process_state` | Typical meaning |
|-----------------|-----------------|
| `idle` | Machine idle |
| `heating` | Process / heating on |
| `gas` | Gas phase |
| `solenoid_on` | Solenoid active |
| `cooling` | Cooling on |
| `n2_purging` | Nitrogen purge |
| `carbon_discharge` | Carbon discharge |
| `main_door_open` | Main door open |
| `unknown` | Unmapped panel text |

Mapping from raw panel strings lives in `backend/src/htpp/ingest/process_map.yaml`.

---

## 2. Plant Excel mass log (optional, for yields)

Uploaded workbooks are parsed with `column_map.yaml`. Header aliases are flexible; required quantities:

| Logical field | Unit | What it is |
|---------------|------|------------|
| Reactor / machine | — | Which unit (matched via `HTPP_MACHINE_ALIASES`) |
| Date | calendar day | Batch day used to join panel batches |
| Loading / feed | kg | Charge mass |
| Moisture | % | Feed moisture |
| Oil | kg | Recovered oil |
| Carbon | kg | Recovered carbon |
| Steel | kg | Recovered steel / wire |
| Gas | kg | Estimated or measured gas (if present) |

If the sheet has **no panel batch number**, the shadow matches by **machine + date (IST)**.

---

## 3. Derived outputs (not PLC)

| Output | Meaning |
|--------|---------|
| Batch / phase table | Segmented runs from process-state changes |
| Yields | Oil / carbon / steel % from Excel + feed |
| Model projection | Smooth temperatures between sparse samples |
| Insights | Operator-facing summaries of gaps, yields, faults |

---

## 4. Privacy

Do not commit:

- `.env` (credentials, API keys, site-specific aliases)
- Live DuckDB databases
- Production Excel exports

Keep display names generic in code (`R1 Unit 1`, …). Put plant-specific Excel reactor text only in `.env` → `HTPP_MACHINE_ALIASES`.
