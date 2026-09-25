# 01 - Product and Research Requirements

## 1. Problem

Plant Operator runs three batch tyre-pyrolysis reactors. Operations today
are driven by a cloud panel that shows current sensor values and a per-batch
phase timeline. The panel is a monitor, not a model. It cannot answer:

- What yield will this batch give, given what we charged into it?
- Is this batch behaving abnormally right now, before the alarm fires?
- How long will this batch actually take?
- Which operating pattern across the three reactors gives the best oil yield?
- Why did reactor 1094 take six hours longer than 1093 on nominally the same charge?

Every one of those is answerable from data that already exists, once the panel
telemetry is joined to the plant's manual batch log and a physically grounded
reduced-order model sits between them.

## 2. Research question

> Can a reduced-order thermal and kinetic model, identified purely from sparse
> industrial batch-pyrolysis telemetry (about 4-minute cadence) and plant mass
> logs, predict product yields and detect process faults earlier than the plant's
> existing threshold alarms?

Three sub-questions, each mapping to a result section:

- **RQ1 (identifiability).** Can effective thermal parameters be identified from
  4-minute telemetry with no measured heat input? Specifically, does the
  unforced cooling phase give a stable estimate of the reactor time constant
  across batches and machines?
- **RQ2 (yield).** Do thermal-severity features derived from the model predict
  oil, carbon black and steel yields better than feed mass alone?
- **RQ3 (fault lead time).** Do model residuals cross a detection threshold
  measurably earlier than the panel raises `Choke Emergency` or
  `Gas Passage Choke`?

RQ3 is the strongest contribution because the panel already supplies labelled
fault events, which industrial datasets almost never do.

## 3. Scope

### In scope

- Historical ingestion of all available panel telemetry for machines 1093, 1094, 1146
- Continuous incremental ingestion going forward
- Ingestion of the plant Excel batch log (feed mass, moisture, oil, carbon, steel)
- Batch segmentation and phase labelling
- Reduced-order lumped-capacitance thermal model, fitted per phase per batch
- Single-step global Arrhenius conversion model linked to measured yields
- Yield prediction model with prediction intervals
- Residual-based fault detection with lead-time evaluation
- Model-based interpolation to produce smooth state at display rate
- FastAPI backend exposing data, models, simulation and a live channel
- Next.js frontend with a real-time 3D scene of all three reactors
- Historical batch replay in 3D with a timeline scrubber
- What-if simulation UI
- Reproducible validation report and paper-ready figures

### Explicitly out of scope

State these as non-goals in the paper. They are not weaknesses if declared.

- **CFD or spatially resolved modelling.** Single lumped zone per vessel only.
  There is one temperature sensor per vessel. Spatial resolution is not
  identifiable and claiming it would be dishonest.
- **Multi-step or distributed-activation-energy kinetics.** No gas composition,
  no TGA data, no intermediate sampling. A single-step global conversion model is
  the most that the data supports.
- **Closed-loop control or setpoint actuation.** No write access to the panel,
  and none should be requested. This is what keeps the project a shadow rather
  than a twin, and it is the correct scope for a first paper.
- **Oil quality prediction.** No calorific value, density, sulphur or
  distillation data.
- **Gas composition or flare modelling.** Not instrumented.
- **Energy efficiency or specific energy consumption.** Fuel and electricity
  input are not measured. Do not fabricate a heat input figure to fill this gap.
- **Anything requiring sub-minute dynamics.** Control loop tuning, valve
  response, safety interlock timing.

## 4. Users and their jobs

| User | Job to be done | Where it lands |
|---|---|---|
| Plant operator | See all three reactors at a glance, spot the one going wrong | 3D overview scene, fault strobes |
| Plant manager | Know expected yield and finish time for a running batch | Live batch panel, prediction intervals |
| Process engineer | Compare batches, understand why one underperformed | Batch explorer, replay, feature diagnostics |
| Researcher (Maddy) | Reproducible results, figures, validation tables | Validation report, notebooks, paper figures |
| Reviewer | Verify claims are supported by the data | Validation protocol doc, held-out results |

## 5. Functional requirements

Each is testable. Cursor must not mark a task done without the stated evidence.

### FR-1 Ingestion
- FR-1.1 Fetch all panel telemetry for all three machines from the earliest
  available date to now, without gaps, and persist it idempotently.
- FR-1.2 Re-running ingestion must not duplicate rows. Uniqueness is
  `(machine_id, sampled_at)`.
- FR-1.3 Incremental ingestion runs on a schedule and fetches only new data.
- FR-1.4 Record per-run ingestion metadata: rows fetched, rows new, date range,
  HTTP errors, duration.
- FR-1.5 Parse the plant Excel batch log through a configurable column mapping,
  so a change in the plant's spreadsheet layout is a config edit and not a code
  change.
- *Evidence:* coverage report showing rows per machine per day with gaps flagged.

### FR-2 Batch assembly
- FR-2.1 Group telemetry into batches using the panel's own `batch_no`.
- FR-2.2 Derive phase segments and durations per batch.
- FR-2.3 Join each batch to its Excel log row on `(machine_id, batch_no)`.
- FR-2.4 Flag batches that are incomplete, that span an ingestion gap, that
  contain a fault label, or whose Excel mass balance does not close within
  tolerance.
- *Evidence:* batch table with a `quality_flags` column and counts per flag.

### FR-3 Modelling
- FR-3.1 Fit cooling-phase time constant per batch. Report distribution per machine.
- FR-3.2 Fit heating-phase effective heat input and loss coefficient per batch.
- FR-3.3 Compute thermal severity features per batch.
- FR-3.4 Fit conversion kinetics so predicted conversion correlates with measured
  combined oil plus gas yield.
- FR-3.5 Fit yield models for oil, carbon and steel with prediction intervals.
- FR-3.6 Produce residual series per batch and a fault detector over them.
- FR-3.7 All model artefacts versioned and loadable by the API without refitting.
- *Evidence:* validation report with held-out metrics against stated baselines.

### FR-4 Simulation
- FR-4.1 Given feed mass, moisture, feedstock mix and a heating profile, simulate
  full trajectories for Tr, Ts, Pr, Ps, predicted phase durations, predicted total
  batch time and predicted yields with intervals.
- FR-4.2 Replay any historical batch and overlay simulated against actual.
- FR-4.3 Live shadow: from the current state of a running batch, project the
  remainder of the batch forward and update every ingestion tick.
- *Evidence:* replay of a held-out batch with error metrics shown in the UI.

### FR-5 3D visualisation
- FR-5.1 Render all three reactors in one scene with correct per-machine state.
- FR-5.2 Every process label in the state vocabulary maps to a distinct, visible
  visual state. See doc 08 for the mapping table. No label may render identically
  to another.
- FR-5.3 Main door position reflects `MAIN DOOR OPEN` versus closed states, animated.
- FR-5.4 Reactor shell appearance reflects reactor temperature on a continuous ramp.
- FR-5.5 Numeric overlay per reactor: Tr, Ts, Pr, Ps, batch number, current phase,
  elapsed time in phase.
- FR-5.6 Scene state updates smoothly at display rate, interpolated by the model,
  never stepping at the 4-minute telemetry cadence.
- FR-5.7 Fault labels produce an unmissable visual alarm localised to the relevant
  component.
- FR-5.8 Clicking a reactor focuses the camera and opens its detail panel.
- FR-5.9 Timeline scrubber replays historical batches through the same scene.
- *Evidence:* recorded screen capture walking through every state in the vocabulary.

### FR-6 Non-functional
- NFR-1 3D scene holds 60 fps with all three reactors on a mid-range laptop GPU.
- NFR-2 Telemetry tick to scene update under 500 ms.
- NFR-3 Full historical refit completes in under 10 minutes on a laptop.
- NFR-4 Scraper issues no more than one request per two seconds and never touches
  a write endpoint.
- NFR-5 No credentials in the repository. `.env` only, `.env.example` committed.
- NFR-6 Every number shown in the UI carries a unit.

## 6. Success criteria

The project succeeds if, at the end of day six, all of the following hold:

1. Coverage report shows complete ingestion of all available panel history for
   all three machines.
2. Cooling-phase time constant is identified for at least 80 percent of complete
   batches, with a coefficient of variation within a machine below 0.3.
   *If this fails, RQ1 is answered negatively, which is still a publishable
   result. Report it, do not hide it.*
3. Yield model beats the feed-mass-only baseline on held-out batches for at least
   oil yield, by a margin larger than the baseline's own standard error.
4. Fault detector achieves positive median lead time against panel alarm
   timestamps, with precision and recall both reported. Negative lead time is
   also a reportable result.
5. 3D scene renders every state in the vocabulary correctly and holds frame rate.
6. `make reproduce` regenerates every figure and table in the validation report
   from raw data.

## 7. Known risks

| Risk | Impact | Mitigation |
|---|---|---|
| Panel trims history before backfill completes | Permanent data loss | Backfill on day one, before anything else |
| Excel log arrives late or is sparse | Yield model has no target | Build against synthetic fixtures conforming to doc 03. Thermal model and fault detection do not depend on Excel |
| Excel mass balance does not close | Targets unreliable | Flag and report closure error distribution. Exclude non-closing batches from training, report how many |
| Blender glTF late | 3D blocked | Placeholder mesh implements the same node contract. Never code against the file |
| Panel changes HTML layout | Scraper breaks | Parser targets column headers by name, not index. Contract test on a saved HTML fixture |
| Heat input unidentifiable without fuel data | Thermal model underdetermined | Identify from unforced cooling first, where heat input is zero. Report heating-phase heat input as an effective lumped parameter, not a physical fuel rate |
| 100 batches is a small sample | Overfitting | Regularised models only, nested CV, report confidence intervals, no deep learning |
| Panel operator objects to scraping | Project stops | Get written consent early. Rate limit. Read-only |

## 8. Feedstock note, needs confirmation

The recovered products named by the plant are oil, carbon and **steel**, with
moisture tracked on the input. Steel recovery plus carbon plus oil is the
signature of **waste tyre pyrolysis**, not plastic pyrolysis. The panel's
`CARBON DISCHARGE` phase is consistent with carbon black removal.

**Confirm with the plant before writing the paper.** The distinction changes the
literature the work sits in, the expected yield ranges for sanity checks, and the
kinetics framing. Do not assume. If it is a tyre and plastic mix, the mix ratio
becomes a required model feature and must be added to the Excel schema.
