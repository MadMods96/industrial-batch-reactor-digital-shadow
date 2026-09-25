# 07 - Frontend Spec

Next.js App Router, TypeScript strict. The 3D scene is specified separately in
doc 08; this document covers everything around it.

---

## 1. The performance rule that shapes the whole frontend

The 3D scene runs at 60 fps. Telemetry-derived values change every frame because
the model-based interpolation plays a dense trajectory. **If those values live in
React state, the scene will drop frames**, because every value change re-renders
the component tree.

So the architecture is:

- **Zustand store, subscribed transiently.** The 3D scene reads live values inside
  `useFrame` through `store.getState()` or `subscribeWithSelector` with a
  non-reactive subscription. It never calls `useStore(selector)` for per-frame values.
- **React state only for things that change at human rate.** Selected machine,
  camera mode, which panel is open, replay position while dragging.
- **The HUD text updates at 10 Hz, not 60 Hz**, via a throttled subscription. No
  human reads a temperature changing sixty times a second, and re-rendering text
  nodes at 60 fps is pure waste.

Concretely:

```ts
// lib/store.ts
interface LiveState {
  machines: Record<number, MachineLive>;   // written by ws.ts, read in useFrame
  modelVersion: string | null;
  connected: boolean;
}

// Per-frame consumers: DO THIS
const m = useLiveStore.getState().machines[machineId];

// Per-frame consumers: NEVER DO THIS
const m = useLiveStore((s) => s.machines[machineId]);  // re-renders every frame
```

Cursor must add an ESLint rule or at minimum a comment banner in
`components/scene/` stating this, because it is the exact mistake that gets made
and it is hard to diagnose afterwards.

---

## 2. Live data pipeline

```
/ws/live  ──►  lib/ws.ts  ──►  zustand LiveState
                                    │
                    ┌───────────────┼────────────────┐
                    ▼               ▼                ▼
             useFrame (60Hz)   HUD (10Hz)      React UI (on event)
             3D scene          numeric text    alarms, panels
```

### `lib/ws.ts` responsibilities

- Connect, handle `snapshot`, `tick` and `alarm` message types.
- Exponential backoff reconnect: 1, 2, 4, 8, 16, 30 s cap. Set `connected: false`
  while down, and the UI shows a reconnecting banner.
- Keepalive ping every 30 s.
- On `tick`, write the new dense trajectory into the store **and record
  `anchorPerfTime = performance.now()`** so the scene knows where in the trajectory
  it is.
- On `alarm`, push to an alarm queue that the UI drains into toasts, and set the
  machine's severity so the 3D scene picks it up on the next frame.

### Playing the dense trajectory

The core of smooth 3D. In `useFrame`:

```ts
// components/scene/useInterpolatedState.ts
export function sampleLive(machineId: number, now: number): InterpolatedState {
  const m = useLiveStore.getState().machines[machineId];
  if (!m) return NEUTRAL;

  const elapsedS = (now - m.anchorPerfTime) / 1000;
  const dense = m.dense;

  // Past the horizon means the next tick is late. Hold the last value and
  // mark stale. NEVER extrapolate past the end of the trajectory.
  if (elapsedS >= dense.horizonS) {
    return { ...lastOf(dense), stale: true };
  }

  const i = Math.min(Math.floor(elapsedS / dense.stepS), dense.trC.length - 2);
  const f = (elapsedS - i * dense.stepS) / dense.stepS;

  let trC = lerp(dense.trC[i], dense.trC[i + 1], f);

  // Blend from the previous trajectory to this one over BLEND_MS so a new
  // tick never causes a visible snap.
  if (now - m.anchorPerfTime < BLEND_MS && m.prevValueAtHandover != null) {
    const b = (now - m.anchorPerfTime) / BLEND_MS;
    trC = lerp(m.prevValueAtHandover.trC, trC, easeOutCubic(b));
  }

  return { trC, tsC, prBar, psBar, processState: denseStateAt(dense, i), stale: false };
}
```

`BLEND_MS = 400`. Handover blending is what separates a scene that looks
professional from one that visibly twitches every four minutes.

**When `stale` is true**, the scene must show it: desaturate that reactor, show a
"telemetry stale" badge with the age. Do not keep animating a projection that has
outrun its data.

---

## 3. Pages

### `/` Plant overview, the landing page

The 3D scene is the page, full-bleed. Overlaid UI:

- Top bar: connection status, model version, last ingest time, global alarm count.
- Three reactor cards along one edge, each showing machine name, current phase,
  `tr_c`, batch number, elapsed time, a residual severity dot. Clicking a card
  focuses that reactor's camera.
- Camera controls: `Overview`, `Reactor 1`, `Reactor 2`, `Reactor 3`, `Cutaway`.
- Alarm toasts, bottom right, colour-coded by severity, persisting until dismissed
  for `critical`.
- A collapsible bottom drawer with a live `tr_c` sparkline per machine over the last
  six hours.

Load the scene with `next/dynamic` and `ssr: false`. Show a lightweight skeleton
while the glTF loads, with a real progress indicator from drei's `useProgress`.

### `/machines/[id]`

- Full telemetry charts: `tr_c`, `ts_c`, `amb_temp_c` on one axis pair; `pr_bar`,
  `ps_bar` on another. Phase bands shaded behind, fault markers as vertical lines.
- Model overlay toggle: measured versus model, with the residual on a secondary axis.
- Date range picker, defaulting to the last 24 hours.
- Current batch projection: predicted end time, predicted yields with intervals,
  displayed as ranges rather than single numbers.
- A small embedded single-reactor 3D view.

### `/batches`

Sortable, filterable table of every batch. Columns: batch key, machine, start,
duration, peak `tr_c`, phase durations, measured yields, predicted yields, closure
error, fault badges, quality flags, and a clear `In training split` indicator.

Filters: machine, date range, has fault, usable for training, has Excel log.
Row click goes to the replay page.

### `/batches/[key]` Replay, the demo page

This is the page to show a plant manager or put in a PhD application.

- Timeline scrubber across the full batch with phase bands.
- Play, pause, and speed controls at 1x, 60x, 600x, 3600x.
- The **same 3D scene component** as the overview, driven by replay data instead of
  live data. Reuse, do not fork. The scene component takes an `InterpolatedState`
  and does not care where it came from.
- Side-by-side charts: measured points against the simulated line. Measured as
  discrete dots, simulated as a continuous curve. **Never join measured points with
  a line**, because at 4-minute cadence that line is an invention.
- Error panel: `tr_rmse_c`, phase duration errors, yield errors.
- Ghost overlay toggle: render a semi-transparent second reactor showing the
  simulated state beside the measured one, so divergence is visible in 3D.
- Prominent badge if this batch was in the training split.

### `/simulate` What-if

- Form: machine, `feed_mass_kg`, `moisture_pct`, `feedstock_type`,
  `target_peak_tr_c`, `heating_power_scale`, `amb_temp_c`.
- Each numeric input shows the training-data range underneath, and turns amber when
  the value leaves it.
- `extrapolation_warnings` from the API render as a **blocking banner**, not a
  subtle hint.
- Results: trajectory chart, predicted phase durations, predicted total time,
  predicted yields as interval bars rather than points.
- Compare mode: hold up to three scenarios side by side.
- Optional: run the simulated trajectory through the 3D scene in fast-forward.

### `/model` Model diagnostics

Renders `/api/models/metrics` verbatim. Every table and figure here should be
paper-ready.

- Held-out metrics per target, against baselines B0, B1, B2, with n shown beside
  every metric.
- Parity plots: predicted against measured, held-out only, with the identity line.
- Residual diagnostics: residual against fitted, residual against `started_at` to
  check for drift, QQ plot.
- Feature importances or Ridge coefficients on standardised features.
- Prediction-interval coverage: nominal against empirical.
- `tau_cool_min` distribution per machine, the RQ1 figure.
- `tau_cool_min` against `feed_mass_kg` scatter, the charge-mass inference result.
- Fault detection: ROC, precision-recall, and the lead-time histogram with median
  and IQR marked. This is the RQ3 figure.
- The steel-yield negative control, explicitly labelled as such.

### `/data` Data quality

- Coverage calendar heatmap, machine by day.
- Gap list with durations.
- Sampling interval distribution.
- Batch counts by quality flag.
- Excel closure error histogram.
- Unmatched Excel rows, with the reason for each.
- Unmapped `process_raw` values, highlighted, since each one is a potential
  unhandled state in the 3D scene.
- Ingest failure log.
- Excel upload dropzone.

---

## 4. Components

```
components/
├── scene/                  # see doc 08
├── charts/
│   ├── TelemetryChart.tsx  # Recharts, phase bands, fault markers
│   ├── ReplayChart.tsx     # measured dots vs simulated line
│   ├── ParityPlot.tsx
│   ├── LeadTimeHistogram.tsx
│   ├── CoverageHeatmap.tsx
│   └── Sparkline.tsx
└── ui/
    ├── ReactorCard.tsx
    ├── ValueWithUnit.tsx       # every number goes through this
    ├── PredictionInterval.tsx  # renders p10/p50/p90 as a bar
    ├── SeverityDot.tsx
    ├── AlarmToast.tsx
    ├── QualityFlagBadges.tsx
    ├── TrainingSplitBadge.tsx
    ├── ExtrapolationWarning.tsx
    ├── StalenessBadge.tsx
    └── TimelineScrubber.tsx
```

### Two components that matter more than they look

**`ValueWithUnit`.** Every displayed number goes through it. It takes a value, a
unit and an optional precision, renders `null` as an em-less "no data" rather than
`0`, and enforces the unit label. This single component is what prevents a
dimensionless number from ever appearing on screen, which in a process-engineering
UI is a real hazard.

**`PredictionInterval`.** Renders p10 to p90 as a bar with p50 marked. Use it
everywhere a prediction appears. Never display a bare p50, because a single number
implies a confidence the model does not have with about 100 training batches.

---

## 5. Design

Dark theme by default, since this is an operations display that may sit on a wall.
Support light mode via `prefers-color-scheme` with tokens on `:root`.

Semantic colours, defined once as CSS custom properties and used by both the 2D UI
and the 3D scene so they agree:

| Token | Use |
|---|---|
| `--ok` | Normal operation |
| `--warning` | Residual elevated, extrapolation, stale approaching |
| `--critical` | Fault active, alarm |
| `--idle` | Machine idle |
| `--stale` | Telemetry stale, desaturated |
| `--measured` | Measured data series |
| `--simulated` | Simulated or projected series |

**`--measured` and `--simulated` must be distinguishable in greyscale**, because
these figures go into a paper that may be printed. Use different line styles too:
measured as dots, simulated as a solid line.

Temperature has its own ramp, specified in doc 08 section 4, and it must be the
same ramp in the charts and in the 3D scene. A reactor that glows deep orange while
its chart shows a blue-green colour is a contradiction the viewer will notice.

Do not use red for any purpose except faults. Not for a temperature series, not
for a chart line. Red must mean one thing in an operations display.

---

## 6. Type generation

Generate TypeScript types from the FastAPI OpenAPI schema with
`openapi-typescript` into `lib/api-types.ts`, as a `make types` target. Never
hand-write response interfaces; they will drift from doc 03 within a day.

`lib/api.ts` is a thin typed fetch wrapper with `snake_case` to `camelCase`
conversion at the boundary and nowhere else.

---

## 7. Error and empty states

Every one of these must be designed, not left to crash:

| Condition | Behaviour |
|---|---|
| WebSocket down | Reconnecting banner, scene holds last state desaturated, no fake motion |
| `staleness_s > 600` | That reactor shows a stale badge with age, desaturated |
| No fitted model yet | `interpolation_mode: linear_fallback` badge in the HUD, predictions hidden entirely, not shown as zero |
| No Excel log for a batch | Measured yields show "not logged", predictions still shown, clearly labelled as unvalidated |
| glTF fails to load | Fall back to the placeholder mesh, show a non-blocking notice. **The app must never be blank because a 3D asset is missing** |
| WebGL unavailable | Full 2D fallback with charts and cards. The whole app must remain usable without 3D |
| Zero batches in database | Onboarding panel saying to run `make backfill` |
| API unreachable | Clear error with the API URL being attempted |

The glTF fallback and the WebGL fallback both matter more than they seem. A demo
to a plant manager on an unknown laptop will hit one of them.
