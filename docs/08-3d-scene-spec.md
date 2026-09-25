# 08 - 3D Scene Spec

React Three Fiber, three reactors in one scene, visual state driven entirely by
telemetry. The glTF asset contract is doc 09; this document defines behaviour.

---

## 1. The rule that keeps this project unblocked

**The scene is coded against the node-name contract in doc 09, never against a
specific file.**

Two implementations satisfy that contract:

- `ReactorPlaceholder.tsx`, procedural geometry from three.js primitives, exposing
  exactly the named nodes doc 09 specifies.
- `ReactorGltf.tsx`, loading `public/models/reactor.glb`.

`Reactor.tsx` picks between them:

```tsx
const gltfAvailable = useGltfProbe("/models/reactor.glb");
return gltfAvailable
  ? <ReactorGltf {...props} />
  : <ReactorPlaceholder {...props} />;
```

Every animation, material and effect hook operates on nodes looked up **by name**.
Swapping in the real Blender export is then dropping a file into `public/models/`.

**Build the placeholder on day four, before the glTF exists.** Do not wait for the
Blender model. If the scene code is written against the real file, the 3D work
cannot start until modelling finishes, and the six-day plan collapses. This is the
single most important sequencing decision in the build.

---

## 2. Scene layout

```
            ┌─────────────────────────────────────────┐
            │   Reactor 1093      1094      1146      │
            │   slot 0          slot 1     slot 2     │
            │     ▓▓             ▓▓          ▓▓       │
            │     ││             ││          ││       │
            │  ═══╧╧═══════════════════════════════   │  shared ground plane
            └─────────────────────────────────────────┘
                         camera orbits here
```

- Three reactor instances along the X axis, spaced 14 units apart, position from
  `scene_slot` in `/api/machines` so layout is stable across reloads.
- Shared ground plane with a subtle industrial grid texture. No infinite void.
- Each reactor group holds its own vessel, door, burner, separator, condenser,
  piping, discharge chute and HUD anchor.
- A floating label above each reactor with its `display_name`, always facing the
  camera (`drei` `Billboard`).

### Lighting

- One `hemisphereLight` at low intensity for ambient fill.
- One `directionalLight` as the key, casting shadows, with a tightly fitted shadow
  camera. A loose shadow frustum is the most common cause of blocky shadows.
- Shadow map 2048 for the key light only. Three shadow-casting lights will not hold
  60 fps.
- `Environment` from drei with a `warehouse` or `city` preset for believable metal
  reflections. Use a preset rather than shipping an HDR, to keep bundle size down.
- **Reactor shell emissive is not a light.** It is an emissive material plus a
  bloom pass. Adding three real point lights inside the vessels will destroy the
  frame rate for no visual gain.

### Post-processing

`@react-three/postprocessing`, in this order:

1. `Bloom`, `luminanceThreshold` 0.6, `intensity` scaled by the hottest reactor's
   temperature. This is what sells the heat.
2. `SSAO`, low radius, for contact shadows in the piping.
3. `ToneMapping`, ACES filmic.

Provide a settings toggle to disable post-processing entirely. It is the first
thing to turn off on a weak GPU, and it must not break the scene when off.

### Camera

| Mode | Behaviour |
|---|---|
| `Overview` | `OrbitControls`, framing all three reactors, gentle auto-rotate when idle |
| `Reactor N` | Animated transition to a framed single reactor, orbit constrained |
| `Cutaway` | Single reactor with the shell's front half hidden, revealing the internal charge volume and carbon bed |

Transitions tween over about 900 ms with an ease-in-out curve. Never cut.
Use `drei` `CameraControls` or a manual lerp of position and target.

---

## 3. State to visual mapping

**This table is the core of the spec. Every `process_state` must produce a visually
distinct result, and no two rows may render the same.** FR-5.2 depends on this.

`process_state` and `fault_state` are **orthogonal**. Faults layer on top of
whatever phase is rendering. A choked reactor that is heating renders heating
visuals plus the choke alarm.

| `process_state` | Door | Shell | Burner | Gas piping | Condenser | Discharge chute | Extra |
|---|---|---|---|---|---|---|---|
| `idle` | closed | temp ramp (cold, dark) | off | still, dim | still | closed | Everything quiet. No motion anywhere |
| `heating` | closed | temp ramp, **rising** | **flame on**, scaled by `roh_c_per_min` | still | still | closed | Heat shimmer above burner. Emissive climbing with `tr_c` |
| `gas` | closed | temp ramp (hot, bright) | flame on, steady | **animated flow**, emissive pulse travelling vessel to separator, speed from `pr_bar` rate of change | **active**, coolant swirl, oil drip at the outlet | closed | The busiest state. Most visual activity of any phase |
| `solenoid_on` | closed | temp ramp | flame on | flow **plus** the solenoid valve body pulsing amber | active | closed | A `gas` variant. Valve body must be individually visible |
| `cooling` | closed | temp ramp, **falling** | **off**, with a brief afterglow fade | flow fading out | winding down | closed | Cooling fan or water jacket animation. Emissive draining away |
| `n2_purging` | closed | temp ramp (warm) | off | **cool blue-white stream** through the N2 line, visually distinct from the hot gas flow | still | closed | Different colour, different line, unmistakably not gas |
| `carbon_discharge` | closed | temp ramp (warm) | off | still | still | **open**, black particle stream falling into a bin | Bin fills progressively over the phase duration |
| `main_door_open` | **open**, hinged animation | temp ramp (warm) | off | still | still | closed | Interior visible. Residual glow inside if `tr_c` is still high |
| `unknown` | closed | flat grey, **no temp ramp** | off | still | still | closed | Visibly neutral plus a magenta "?" badge. Must look wrong, so unmapped states get noticed |

| `fault_state` | Visual, layered on top |
|---|---|
| `none` | nothing |
| `choke_emergency` | **Red strobe** at the gas outlet, 2 Hz. Outlet pipe pulses red. Red warning beacon on the reactor top spins. HUD border turns critical red |
| `gas_passage_choke` | **Amber-to-red strobe** on the gas passage pipe specifically, between vessel and separator. Flow animation stutters and backs up, which reads as a blockage. Localise it, do not flash the whole reactor |
| `pressure_sensor_error` | Pressure gauge face flashes, needle goes limp to zero, a small sensor badge on the vessel turns red. **The shell does not alarm**, because this is an instrument fault not a process fault |
| `unknown_fault` | Magenta strobe plus the raw panel string in the HUD |

### Non-negotiables in this table

- **`gas_passage_choke` must be localised** to the passage between vessel and
  separator. That is the whole diagnostic value: an operator should see *where* the
  problem is, not just that there is one.
- **`n2_purging` must not look like `gas`.** Different line, different colour
  temperature. These are the two states most likely to be conflated, and they mean
  completely different things.
- **`pressure_sensor_error` must not alarm the shell.** An instrument fault that
  looks like a process emergency trains operators to ignore alarms.
- **`unknown` must look broken.** It is a developer signal, not a valid state. If
  it renders plausibly, an unmapped panel string will go unnoticed for weeks.

---

## 4. Temperature ramp

One function, used by the 3D scene **and** the 2D charts, so they never disagree.

```ts
// components/scene/tempRamp.ts
export function tempToShell(trC: number): {
  emissive: THREE.Color;
  emissiveIntensity: number;
  baseColor: THREE.Color;
}
```

Physically motivated black-body-ish progression, with control points:

| `tr_c` | Emissive | Intensity | Reads as |
|---|---|---|---|
| ≤ 100 | near black | 0.00 | Cold steel, base colour only |
| 200 | very dark red | 0.05 | Barely warm |
| 300 | dark red | 0.20 | Warming |
| 400 | deep red | 0.50 | Hot |
| 450 | red-orange | 0.75 | Operating temperature |
| 500 | orange | 1.00 | Hot operating |
| 600 | bright orange | 1.40 | Very hot |
| ≥ 700 | orange-yellow | 1.80 | Above normal, should be rare |

Interpolate in **OKLab or HSL, not linear RGB.** Linear RGB interpolation through
dark reds goes muddy brown, which looks wrong and unphysical.

Rules:

- Base colour is a dark industrial steel with roughness around 0.6 and metalness
  around 0.8, unchanged by temperature. Only emissive varies, which is what real
  hot steel does.
- `emissiveIntensity` feeds the bloom threshold, so glow blooms naturally at high
  temperature.
- **Never let the shell go fully black at ambient.** It must remain readable as a
  metal object. Base colour plus environment reflection handles this.
- Observed `tr_c` reached 468 degC on a real batch, so 400 to 500 is the visually
  important band. Tune the ramp so that band has the most perceptual resolution,
  since that is where operators will read it.
- Do **not** apply this ramp to the separator using `tr_c`. The separator uses
  `ts_c`, which runs much cooler (26 degC when the reactor was at 34 degC, 193 degC
  when the reactor was hot). They are genuinely different temperatures and must
  look different.

---

## 5. Animation details

### Door, the feature that was explicitly asked for

- A single hinge rotation on the `Door_Hinge` node about its local Y axis, from
  0 to about 100 degrees.
- Drive a `doorOpen` value from 0 to 1 by target state, then ease it:
  `easeInOutCubic`, 2.5 seconds. An industrial door on a 26-hour batch should feel
  heavy. A snappy 300 ms door looks like a toy.
- **`main_door_open` in the data means already open.** On a live tick that arrives
  with the door open, do not animate from closed; set `doorOpen = 1` immediately on
  first observation, and animate only on an observed transition. Otherwise every
  page refresh plays a spurious door opening.
- In replay, animate the transition properly, since the timeline gives real ordering.
- Reveal the interior when `doorOpen > 0.3`: the internal charge volume, plus
  residual emissive glow scaled by `tr_c`.

### Burner flame

- A cone with a custom shader, or an additive-blended sprite sheet. Do not use a
  particle system with thousands of particles; three flames at 60 fps do not need it.
- Height and intensity scale with `roh_c_per_min` during `heating`, and sit at a
  steady baseline during `gas`.
- Animate with a noise-driven flicker in the shader, using `uTime`. A perfectly
  steady flame reads as fake.
- Afterglow on transition to `cooling`: fade over about 4 seconds rather than
  cutting.

### Gas flow

- Emissive pulses travelling along the pipe, from an animated offset on a texture
  UV or a shader `uTime` term. A sequence of instanced meshes moving along a curve
  also works and is easier to debug.
- Speed from the rate of change of `pr_bar`, clamped to a legible range. Do not let
  a pressure spike make the animation strobe.
- On `gas_passage_choke`, make the flow **stutter and accumulate** at the
  restriction. That visual reads instantly as a blockage and is the single most
  valuable frame in the whole scene.

### Carbon discharge

- A particle stream from the chute into a bin, `points` with an additive material,
  a few hundred particles.
- Bin fill level rises with phase progress: `phase_elapsed_min / expected_duration`.
  The model supplies the expected duration, so the fill is a model output too.
- Dark, matte particles. Carbon black is not shiny.

### N2 purge

- A cool blue-white stream along the **N2 line specifically**, a different pipe
  from the gas line.
- Slight volumetric haze at the outlet. A `Cloud` from drei or a simple
  additive-blended plane; do not add real volumetric rendering.

### Fault strobes

- Emissive pulse at 2 Hz driven by `Math.sin(uTime * Math.PI * 2 * 2)`.
- Localised to the named node the fault belongs to, never the whole reactor except
  for `choke_emergency`, which is genuinely a whole-reactor emergency.
- Also drive a `Beacon_Light` node's rotation so there is motion, not just colour.
  Colour-only alarms are easy to miss in peripheral vision.
- Respect `prefers-reduced-motion`: replace strobes with a steady colour plus a
  persistent HUD badge. Flashing at 2 Hz is a genuine accessibility concern.

---

## 6. HUD

A `drei` `Html` panel anchored to each reactor, or a screen-space overlay
positioned by projecting the reactor's world position. Screen-space is easier to
keep legible and is preferred.

Per reactor:

```
┌──────────────────────────────┐
│ Plant Operator - 1      │
│ Batch 833  ·  MAIN DOOR OPEN │
│ ───────────────────────────  │
│ Tr   34.0 °C     Ts  26.0 °C │
│ Pr  -0.01 bar    Ps  0.00 bar│
│ Phase elapsed      1 h 44 min│
│ Batch elapsed     26 h 17 min│
│ ───────────────────────────  │
│ Residual  ● ok        +0.4°C │
│ Model     ✓ model-based      │
│ Predicted end      03:10 IST │
│ Oil yield      38.1–45.4 %   │
└──────────────────────────────┘
```

Requirements:

- **Update at 10 Hz, not 60 Hz.** Throttled store subscription.
- Every value through `ValueWithUnit`. No bare numbers.
- `Residual` is a coloured dot plus the value: `ok`, `warning`, `critical` from the
  WebSocket `residual.severity`.
- `Model` shows `model-based` or `linear fallback`, from `interpolation_mode`.
  The scene must never imply model backing it does not have.
- Predicted yield as a **range**, never a point estimate.
- If `staleness_s > 600`, replace the whole body with a stale warning showing the
  age of the last sample.
- Render times in Asia/Kolkata with the timezone shown.
- Collapsible to a single line, since three expanded HUDs crowd the overview.

---

## 7. Performance budget

Target 60 fps on integrated graphics. Hard floor 30 fps.

| Rule | Reason |
|---|---|
| Total scene under about 150k triangles, so under 50k per reactor | The main lever on GPU cost, and the Blender model must be budgeted for it. See doc 09 |
| Load the reactor glTF **once**, reuse with `useGLTF` and clone the scene graph three times | Loading the same file three times triples memory for nothing |
| One shadow-casting light | Each shadow map is a full extra render pass |
| No per-frame object allocation in `useFrame` | Reuse `THREE.Color` and `THREE.Vector3` instances held in refs. Allocating in `useFrame` causes GC stutter, and it is the most common R3F performance bug |
| No React state writes in `useFrame` | Guaranteed frame drops. See doc 07 section 1 |
| Particle counts: carbon stream under 500, no other particle systems | |
| Textures at 1024, 2048 only where genuinely needed | |
| `dispose()` on unmount, verified with a mount/unmount loop | Navigating between pages repeatedly must not grow memory |
| `<AdaptiveDpr />` and `<AdaptiveEvents />` from drei | Automatic degradation under load |
| Instrument with `r3f-perf` in development, behind a flag | |

Acceptance: navigate between `/` and `/batches` twenty times and confirm memory
returns to baseline. R3F memory leaks are easy to create and invisible until a
wall display crashes after six hours.

---

## 8. Replay mode

The scene component is **reused unchanged.** It accepts an `InterpolatedState` and
does not know whether the source is live or replay.

```tsx
<PlantScene
  source={mode === "live"
    ? { kind: "live" }
    : { kind: "replay", batchKey, positionS, speed }}
/>
```

Replay specifics:

- Interpolate through the replay trajectory by `positionS` rather than
  `performance.now()`.
- The `ghost` toggle renders a second semi-transparent reactor at a slight offset
  showing the **simulated** state beside the measured one. Divergence becomes
  visually obvious, which is the most persuasive demonstration of the model in the
  whole project.
- At 3600x speed, do not attempt to animate every transition. Snap door and phase
  states, keep the temperature ramp continuous.
- Scrubbing must be responsive: precompute the replay trajectory into typed arrays
  on load so seeking is an array index, not a request.

---

## 9. Build order for the 3D work

Sequenced so something is on screen early and nothing blocks on the Blender file.

1. `PlantScene` with three grey boxes, ground plane, lights, `OrbitControls`.
   Verify 60 fps. No data.
2. Wire the WebSocket and the zustand store. Print live `tr_c` as HUD text over the
   boxes. **Verify smooth interpolation before any modelling of geometry**, because
   if the interpolation is wrong, nothing built on top of it will look right.
3. `ReactorPlaceholder` with named nodes: vessel cylinder, door with a hinge pivot,
   burner cone, separator cylinder, condenser box, three pipes, chute. Ugly is fine.
   The node names must match doc 09 exactly.
4. Temperature ramp on the vessel. This is the first moment the scene feels alive.
5. Door animation. The explicitly requested feature.
6. Phase-driven visuals, working down the doc 08 section 3 table in order.
7. Fault strobes and beacon.
8. HUD.
9. Camera modes and cutaway.
10. Replay and ghost overlay.
11. Swap in `reactor.glb` when it lands. If steps 3 to 10 were built against names,
    this step is a file copy and a bounding-box adjustment.
12. Post-processing and performance tuning last, because it is the easiest thing to
    cut if time runs short.
