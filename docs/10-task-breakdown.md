# 10 - Six-Day Task Breakdown

Each task has an ID, a dependency, and **acceptance criteria that must be
demonstrated before the task is marked done.** Cursor may not mark a task complete
on the basis that the code exists. The stated evidence must be produced.

Parallel tracks, so the Blender work never blocks the build:

- **Track A, backend and data.** Days 1 to 3, then modelling.
- **Track B, frontend and 3D.** Days 3 to 5.
- **Track C, Blender asset.** Runs alongside from day 1, three delivery passes.

---

## Day 0, half a day, before the clock starts

| ID | Task | Acceptance |
|---|---|---|
| D0.1 | Scaffold monorepo per doc 02 section 2 | `make setup` completes on a clean machine |
| D0.2 | `.env.example`, `config.py` with pydantic-settings | `python -c "from htpp.config import settings; print(settings.machine_ids)"` prints the three ids |
| D0.3 | `schemas.py` mirroring doc 03 exactly | A review confirming every field, type and unit suffix matches doc 03 |
| D0.4 | DuckDB DDL for all tables in doc 03 | `make build` on an empty database creates every table |
| D0.5 | Ask the plant: feedstock type, moisture basis, wet or dry feed mass, machine names for 1094 and 1146, Excel file | Questions sent. Do not wait for answers to proceed |

---

## Day 1, ingestion. The urgent day.

**History is being trimmed. Backfill must complete today.** Nothing else on this day
matters as much.

| ID | Task | Depends | Acceptance |
|---|---|---|---|
| D1.1 | `panel_client.py` with rate limiter, path allowlist, login, cookie persistence, session-expiry detection by content | D0.2 | Unit test proves a forbidden path raises. Manual test confirms an authenticated fetch of `graph.php` |
| D1.2 | Save a real `graph.php` response as `tests/fixtures/graph_1093.html` | D1.1 | Fixture committed, under 1 MB gzipped |
| D1.3 | `panel_parser.py`, header-name driven, with `SchemaDriftError` | D1.2 | Contract test passes: exact row count, first and last timestamps, hand-verified values for one row |
| D1.4 | `process_map.yaml` plus mapping logic with fault carry-previous | D1.3 | Every `process_raw` in the fixture maps to a non-unknown state. Test asserts carry-previous behaviour on a synthetic fault sequence |
| D1.5 | `store/writes.py` idempotent upsert on `(machine_id, sampled_at)` | D0.4 | Test inserts the same batch twice, row count unchanged |
| D1.6 | Raw HTML archiving to `data/raw/` gzipped | D1.1 | Files present after a fetch |
| D1.7 | History-floor bisection per machine | D1.3 | Prints a discovered floor per machine, matching the manual finding of between 2026-08-03 and 2026-08-15 for 1093 |
| D1.8 | **`make backfill`, full history, all three machines** | D1.5, D1.7 | Coverage table printed. Expect roughly 40k to 50k rows. Exits non-zero on any permanent chunk failure |
| D1.9 | `incremental.py` plus APScheduler job | D1.8 | Two consecutive ticks; the second inserts only genuinely new rows |
| D1.10 | `ingest_runs` recording, including zero-row responses | D1.5 | Table populated after backfill, with zero-row chunks distinguishable from failures |
| D1.11 | Machine-name discovery from `downloaddata.php` and dashboards | D1.1 | Names for 1093, 1094, 1146 printed and written into `column_map.yaml` |
| D1.12 | `make coverage` report | D1.10 | Report shows rows per machine per day, gaps, median intervals |

**Day 1 gate:** if `make backfill` has not completed successfully, do not move to
day 2. Everything downstream depends on this data, and the data is disappearing.

---

## Day 2, batches and features

| ID | Task | Depends | Acceptance |
|---|---|---|---|
| D2.1 | `segment.py`, telemetry to batches to phases | D1.8 | **Reproduces machine 1093 batch 833 exactly**: six phases with the durations in doc 03 section 3, to within one sample interval. Committed as a test |
| D2.2 | `quality.py`, all flags from doc 03 section 6 | D2.1 | Flag counts printed. `had_fault` batches are **not** excluded from training |
| D2.3 | `excel_log.py`, config-mapped parser | D0.3 | Parses the synthetic fixture. A missing required column produces a hard failure naming headers found |
| D2.4 | Synthetic `tests/fixtures/batch_log.xlsx` matching doc 03 section 4 | D0.3 | Covers all three machines, about 100 rows, deliberately includes two non-closing rows and one unresolvable machine name |
| D2.5 | `batch_yields` derived table with closure computation | D2.3 | Closure error distribution printed. `mass_balance_impossible` rows flagged |
| D2.6 | `features.py`, every feature in doc 03 section 5 | D2.1, D2.5 | `batch_features` table populated. Severity index hand-verified against a trapezoid integration on one batch |
| D2.7 | `usable_for_training` computed in exactly one place | D2.2 | Count printed, with a per-flag breakdown of exclusions |
| D2.8 | Cross-check our phase durations against the panel's dashboard timeline | D2.1, D1.9 | Disagreements listed. Agreement within one sample interval on at least 90 percent of phases |

**Day 2 gate:** batch 833 reproduces exactly. If the segmenter is wrong, every
downstream model is fitted on nonsense.

---

## Day 3, models and API

| ID | Task | Depends | Acceptance |
|---|---|---|---|
| D3.1 | `thermal.py` M1.1 cooling tau fit | D2.6 | `tau_cool_min` fitted for at least 80 percent of complete batches. Distribution per machine with CV reported. **This is the RQ1 result, report it whatever it says** |
| D3.2 | M1.2 UA and C separation via regression on `feed_mass_kg` | D3.1 | Scatter plot of `tau_cool` against `feed_mass_kg` with fit and R². `cp_charge` literature value cited with a real source |
| D3.3 | M1.3 heating-phase `Q_H` and `tau_h` fit | D3.1 | Fitted per batch. Cross-validation plot against panel `roh_c_per_min` |
| D3.4 | M1.4 gas-phase `Q_rxn` and `E_rxn` | D3.3 | `E_rxn` against measured oil plus gas mass, with correlation reported |
| D3.5 | `kinetics.py` M2, fitted on the training split only | D3.4 | `alpha_final` per batch. Held-out correlation with volatile yield reported |
| D3.6 | `yield_model.py` M3 with baselines B0, B1, B2 | D2.7, D3.5 | Held-out metrics for all three targets against all three baselines, n shown. **Steel negative control passes**: thermal features have near-zero importance for steel |
| D3.7 | Prediction intervals, conformal preferred | D3.6 | Empirical coverage against nominal reported on held-out data |
| D3.8 | `faults.py` M4, EWMA and CUSUM | D3.3 | Lead-time distribution against panel alarms, median and IQR. Precision, recall, false alarms per batch. Matching window stated up front |
| D3.9 | `simulate.py` M5 rollout and replay | D3.6 | Held-out batch replay with trajectory RMSE, phase duration errors, yield errors |
| D3.10 | `interpolate.py` M6 dense trajectory with clamping | D3.9 | 300 points at 1 s returned. Test proves a diverging solve is caught and falls back |
| D3.11 | `registry.py`, artefacts including `split_manifest.json` | D3.6 | `make fit` writes a versioned directory. API loads it without refitting |
| D3.12 | FastAPI: all endpoints in doc 06 | D3.11 | OpenAPI schema complete. Every endpoint returns a validated response |
| D3.13 | `/ws/live` with snapshot, tick, alarm | D3.10, D1.9 | A WebSocket client receives a snapshot on connect and a tick on the next ingestion |
| D3.14 | `make reproduce` end to end | D3.11 | Regenerates every metric and figure from the database, no manual steps |

**Day 3 gate:** `/ws/live` is emitting dense trajectories. Track B cannot start
without it.

---

## Day 4, frontend foundation and scene skeleton

| ID | Task | Depends | Acceptance |
|---|---|---|---|
| D4.1 | Next.js scaffold, Tailwind, design tokens from doc 07 section 5 | D0.1 | Dark and light both render |
| D4.2 | `make types` generating TS from OpenAPI | D3.12 | `lib/api-types.ts` generated, no hand-written response interfaces |
| D4.3 | `lib/store.ts` and `lib/ws.ts` with reconnect | D3.13 | Live values visible in a debug panel. Reconnect verified by restarting the API |
| D4.4 | `useInterpolatedState` with blend handover | D4.3 | **Smooth motion verified visually across at least three real ticks.** Plot the interpolated value against time and confirm no step, no snap, no drift past the horizon |
| D4.5 | `PlantScene` with three boxes, lights, ground, OrbitControls | D4.1 | 60 fps with `r3f-perf` confirming |
| D4.6 | `ReactorPlaceholder` with every node name from doc 09 | D4.5 | `validate-gltf.ts` logic passes against the placeholder's node graph. Ugly is acceptable |
| D4.7 | `tempRamp.ts` shared by scene and charts | D4.6 | Reactor shell colour tracks live `tr_c`. Chart uses the identical ramp |
| D4.8 | **Door animation on `Door_Hinge`** | D4.6 | Door opens on `main_door_open`, 2.5 s ease. Already-open state on first observation does **not** animate |
| D4.9 | `ValueWithUnit` and `PredictionInterval` | D4.2 | Every number on screen carries a unit. No bare p50 anywhere |
| D4.10 | HUD at 10 Hz throttle | D4.3 | HUD shows every field in doc 08 section 6. Confirm the React tree does not re-render at 60 fps, via React DevTools profiler |

**Day 4 gate:** D4.4 smooth interpolation. If the scene steps or snaps, stop and fix
it before building any further visuals on top.

---

## Day 5, full 3D behaviour and pages

| ID | Task | Depends | Acceptance |
|---|---|---|---|
| D5.1 | `stateMapping.ts` implementing the full doc 08 section 3 table | D4.8 | **Every `process_state` renders distinctly.** Screen capture walking through all nine states, no two alike |
| D5.2 | Burner flame, shader-driven, scaled by `roh_c_per_min` | D5.1 | Visible during heating and gas, afterglow fade into cooling |
| D5.3 | Gas flow animation with choke stutter | D5.1 | Flow visible during gas. On `gas_passage_choke` it stutters and accumulates **at `Pipe_Gas_Passage` specifically** |
| D5.4 | Carbon discharge particles and bin fill | D5.1 | Chute opens, particles fall, `Carbon_Bin_Fill` scales with phase progress |
| D5.5 | N2 purge stream, visually distinct from gas | D5.1 | Side-by-side capture confirming `n2_purging` and `gas` are unmistakable |
| D5.6 | Fault strobes, localised, plus beacon rotation | D5.1 | All four fault states render correctly. `pressure_sensor_error` does **not** alarm the shell. `prefers-reduced-motion` replaces strobes with steady colour |
| D5.7 | Camera modes including cutaway | D4.5 | All five modes, 900 ms eased transitions |
| D5.8 | `/` overview page with cards and alarm toasts | D5.1 | Full-bleed scene, three cards, click focuses camera |
| D5.9 | `/machines/[id]` with charts and phase bands | D4.7 | Measured as dots, model overlay as a line, fault markers present |
| D5.10 | `/batches` table with all columns and filters | D3.12 | Sortable, filterable, `In training split` visible |
| D5.11 | `/data` coverage page | D1.12 | Heatmap, gaps, closure histogram, unmapped process values highlighted |
| D5.12 | WebGL and glTF fallbacks | D4.6 | Disable WebGL, app remains fully usable in 2D. Delete the glb, placeholder loads with a notice |

---

## Day 6, replay, simulate, validation, writeup

| ID | Task | Depends | Acceptance |
|---|---|---|---|
| D6.1 | `/batches/[key]` replay with scrubber and speeds | D3.9, D5.1 | Scrub through a full 26 h batch. Snapping at 3600x, continuous temperature |
| D6.2 | Ghost overlay, simulated beside measured in 3D | D6.1 | Divergence visible on a held-out batch |
| D6.3 | `/simulate` with extrapolation warnings | D3.12 | Out-of-range input produces a **blocking** banner, not a hint |
| D6.4 | `/model` diagnostics page | D3.11 | Every figure in doc 07 section 3 present and paper-ready |
| D6.5 | Swap in `reactor.glb` | C3, D4.6 | Loads, upright, correct scale, `validate-gltf.ts` passes, door still animates |
| D6.6 | Post-processing and performance pass | D5.1 | 60 fps on integrated graphics with all three reactors. Memory returns to baseline after 20 navigations |
| D6.7 | Validation report generated by `make reproduce` | D3.14 | Every RQ answered with numbers and n. Negative results included |
| D6.8 | Paper figures exported at publication resolution | D6.7 | All figures from doc 11 section 3, greyscale-legible |
| D6.9 | Screen recording walkthrough | D6.1 | Covers every state, a replay, a simulation, and a fault |
| D6.10 | README quickstart verified on a clean clone | all | Someone else can reach a running app from the README alone |

---

## Track C, Blender, running throughout

| ID | Day | Task | Acceptance |
|---|---|---|---|
| C1 | 1 | **Blockout pass.** Primitives, exact names, correct pivots, no detail | doc 09 section 7 checklist passes. Door hinge test passes. This is the critical deliverable |
| C2 | 3 to 4 | **Modelled pass.** Real geometry, materials assigned, untextured | Under 50k triangles. Loads clean in the glTF viewer |
| C3 | 5 to 6 | **Finished pass.** Baked textures, wear, labels | Under 8 MB. Purely visual, no structural change |

C1 is due **day 1**, and it is roughly two hours of work. It converts the asset from
a project blocker into a pure upgrade. Do not let it slip.

---

## Cut list, in order, if time runs short

Cut from the bottom up. Nothing above a cut line may be sacrificed for something below it.

1. `Cutaway` camera mode
2. Post-processing (bloom, SSAO)
3. Ghost overlay in replay
4. Condenser oil-drip detail
5. Gradient boosting comparison, keep Ridge only
6. `/simulate` compare mode
7. C3 textured pass, ship on C2

**Never cut, at any cost:**

- The day-1 backfill. The data is disappearing.
- The batch 833 segmentation test. Everything is built on it.
- The steel-yield negative control. It is the leakage check.
- Baselines B0, B1, B2. Without them there is no result.
- `split_manifest.json`. Without it the results are not auditable.
- Extrapolation warnings. Without them the tool is misleading.
- Model-based interpolation. Without it the 3D scene is decoration.
- The WebGL fallback. A demo will hit it.

---

## Honest timeline note

Six days is achievable for tracks A and B **provided** the Blender blockout lands on
day 1 and the Excel log arrives by day 2. If either slips:

- **Blender slips:** ship on the placeholder mesh. The project is fully functional
  without the glTF, it just looks schematic. This is a cosmetic loss, not a
  functional one.
- **Excel slips:** the thermal model, RQ1 and RQ3 all proceed normally, because none
  of them need the Excel. Only RQ2, yield prediction, is blocked. Build against the
  synthetic fixture and swap in real data when it arrives. Say clearly in the writeup
  that yield results are pending real logs rather than presenting fixture results as
  findings.

Track A on its own is a complete, publishable piece of work. The 3D scene and the
yield model are both additive. Sequence accordingly, and if something has to give,
protect the data and the thermal model.
