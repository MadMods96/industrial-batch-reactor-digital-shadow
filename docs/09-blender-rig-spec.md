# 09 - Blender Rig Contract

**This is a contract, not a suggestion.** The frontend looks up every animated part
by node name. A node named differently, parented differently, or with its pivot in
the wrong place will silently fail to animate, and the failure will look like a code
bug rather than an asset problem.

Hand this document to whoever builds the model, including if that is Maddy.

---

## 1. Why the contract exists

The scene code is written before the model exists. Both the placeholder procedural
mesh and the final Blender export implement the same named interface, so the real
asset drops in without touching scene code.

Practically, this means the Blender work and the code work happen **in parallel**,
which is what makes six days achievable. If the model is built first and the code
second, the timeline does not work.

---

## 2. Export settings

| Setting | Value | Why |
|---|---|---|
| Format | glTF 2.0 binary, `.glb` | Single file, textures embedded |
| Filename | `reactor.glb` | Placed at `frontend/public/models/reactor.glb` |
| Up axis | +Y | three.js convention. Blender is +Z, so the exporter's `+Y Up` must be ticked |
| Units | metres, 1 Blender unit = 1 m | |
| Scale | Real-ish scale. Vessel around 3 m long, 1.6 m diameter | Lighting and camera framing assume plausible dimensions |
| Origin | World origin at the **base centre of the reactor vessel**, on the ground plane | The scene positions reactors by `scene_slot` and expects the base to sit at y=0 |
| Transforms | Apply all modifiers. No parent-inverse matrices. No negative scale | Negative scale flips normals on export and produces inside-out geometry |
| Materials | Principled BSDF only | The only node group glTF reliably exports |
| Textures | Baked, 1024 default, 2048 only where needed, PNG | |
| Animation | **None. Do not author any Blender animation** | All motion is code-driven. Exported animation clips will conflict |
| Cameras / lights | Excluded | Scene provides its own |
| Compression | Draco off for the first delivery | Easier to debug. Enable later if size is a problem |

Target file size under 8 MB. Above that, first-load time on a plant laptop becomes
noticeable.

---

## 3. Triangle budget

Total scene budget is about 150k triangles for three reactors, so **under 50k
triangles per reactor**, hard ceiling.

| Component | Budget |
|---|---|
| `Vessel_Shell` | 8,000 |
| `Vessel_Interior` | 3,000 |
| `Door` assembly | 6,000 |
| `Burner` assembly | 4,000 |
| `Separator` | 5,000 |
| `Condenser` | 6,000 |
| Piping, all | 8,000 |
| `Discharge_Chute` + `Carbon_Bin` | 4,000 |
| Frame, ladders, details | 5,000 |
| Gauges, sensors, beacon | 1,000 |
| **Total** | **50,000** |

Guidance: cylinders at 24 to 32 sides, not 64. Pipes at 12 sides. No subdivision
surface modifiers left unapplied at low poly counts. Bevels only on silhouette
edges that the camera actually sees. Detail that only reads in a close-up of a part
the camera never frames is wasted budget.

---

## 4. Node hierarchy and names

Names are **case-sensitive and exact.** Blender's `.001` suffix on duplicates will
break lookups, so check every name in the Outliner before export.

```
Reactor                          (empty, root)
├── Vessel
│   ├── Vessel_Shell             ← temperature emissive ramp target
│   ├── Vessel_Interior          ← visible through open door, emissive glow
│   ├── Vessel_Insulation
│   └── Vessel_Supports
│
├── Door_Hinge                   ← EMPTY. Pivot for door rotation. CRITICAL
│   └── Door
│       ├── Door_Plate
│       ├── Door_Flange
│       ├── Door_Bolts
│       └── Door_Handle
│
├── Burner
│   ├── Burner_Body
│   ├── Burner_Nozzle
│   └── Burner_Flame_Anchor      ← EMPTY. Flame effect spawns here, points +Y or along the nozzle
│
├── Separator
│   ├── Separator_Shell          ← separate ts_c emissive ramp target
│   └── Separator_Supports
│
├── Condenser
│   ├── Condenser_Body
│   ├── Condenser_Coils
│   └── Condenser_Outlet         ← EMPTY. Oil drip effect anchor
│
├── Piping
│   ├── Pipe_Gas_Passage         ← vessel to separator. gas_passage_choke strobes HERE
│   ├── Pipe_Separator_Condenser
│   ├── Pipe_N2_Line             ← n2_purging stream. MUST be geometrically distinct from the gas line
│   ├── Pipe_Gas_Outlet          ← choke_emergency strobes here
│   └── Valve_Solenoid           ← solenoid_on pulses this body
│
├── Discharge
│   ├── Discharge_Chute          ← opens during carbon_discharge
│   ├── Discharge_Chute_Hinge    ← EMPTY. Pivot for the chute
│   ├── Discharge_Particle_Anchor ← EMPTY. Carbon particle stream origin
│   └── Carbon_Bin
│       └── Carbon_Bin_Fill      ← scales on Y to show fill level. See section 6
│
├── Instruments
│   ├── Gauge_Pressure_Reactor
│   │   └── Gauge_Needle_Pr      ← rotates with pr_bar
│   ├── Gauge_Pressure_Separator
│   │   └── Gauge_Needle_Ps      ← rotates with ps_bar
│   ├── Sensor_Badge_Pressure    ← turns red on pressure_sensor_error
│   └── Beacon_Light             ← rotates and emits during any fault
│
├── Frame
│   ├── Frame_Structure
│   ├── Frame_Ladder
│   └── Frame_Platform
│
└── HUD_Anchor                   ← EMPTY. HUD panel attaches here, above and beside the vessel
```

### The critical pivots

Three empties carry pivot semantics. **Getting these wrong is the most likely
failure mode of the whole asset**, because the code will rotate the node and the
geometry will swing through the wrong arc.

**`Door_Hinge`**
- An **Empty** (plain axes), not a mesh.
- Positioned exactly on the physical hinge axis at the edge of the door flange.
- `Door` and all its children parented to it.
- Local **Y axis aligned with the hinge axis**, vertical.
- Zero rotation in the closed position, so the code animates `rotation.y` from
  `0` to about `1.75` radians.
- **Test in Blender before export:** rotate `Door_Hinge` on Y by 100 degrees. The
  door must swing open cleanly on its hinge, with no intersection of the flange and
  no drift away from the vessel. If it slides or pivots from the middle, the empty
  is in the wrong place.

**`Discharge_Chute_Hinge`**
- Same construction, for the chute. Code animates `rotation.x`.

**`Burner_Flame_Anchor`**
- Empty at the nozzle mouth, its local +Y pointing in the flame direction.
- Code attaches the flame cone here and scales it along local Y.

**`HUD_Anchor`**
- Empty about 1 m above and 1.5 m to the side of the vessel top, where a floating
  panel will not intersect geometry from the overview camera angle.

---

## 5. Materials

Named exactly, because the code overrides properties by material name.

| Material | Applied to | Base colour | Roughness | Metalness | Code modifies |
|---|---|---|---|---|---|
| `Mat_Shell_Steel` | `Vessel_Shell` | dark steel | 0.60 | 0.80 | `emissive`, `emissiveIntensity` from `tr_c` |
| `Mat_Interior` | `Vessel_Interior` | near black | 0.90 | 0.30 | `emissive` from `tr_c` |
| `Mat_Separator_Steel` | `Separator_Shell` | dark steel | 0.60 | 0.80 | `emissive` from **`ts_c`**, not `tr_c` |
| `Mat_Insulation` | `Vessel_Insulation` | light grey | 0.85 | 0.05 | none |
| `Mat_Pipe_Steel` | all pipes | mid steel | 0.45 | 0.90 | `emissive` for flow pulses and strobes |
| `Mat_Pipe_N2` | `Pipe_N2_Line` | pale blue tint | 0.45 | 0.90 | `emissive` for the purge stream |
| `Mat_Valve` | `Valve_Solenoid` | brass or dark | 0.50 | 0.85 | `emissive` pulse |
| `Mat_Frame` | frame, ladder, platform | industrial yellow-grey | 0.75 | 0.60 | none |
| `Mat_Carbon` | `Carbon_Bin_Fill` | near black matte | 0.95 | 0.00 | `scale.y` only |
| `Mat_Gauge_Face` | gauge faces | off-white | 0.40 | 0.00 | `emissive` flash on sensor error |
| `Mat_Beacon` | `Beacon_Light` | red translucent | 0.30 | 0.00 | `emissive` strobe |
| `Mat_Door_Steel` | door parts | dark steel | 0.55 | 0.85 | `emissive` from `tr_c`, reduced |

Rules:

- **Set `emissive` to black in Blender for every material.** The code drives all
  emission. A baked-in emissive value will fight the code and produce a reactor
  that glows while idle.
- **Do not share one material across parts that animate independently.** If
  `Pipe_Gas_Passage` and `Pipe_Gas_Outlet` share a material instance, strobing one
  strobes both, and the localised-fault requirement in doc 08 breaks. Either give
  them distinct materials or accept that the code will clone the material per mesh,
  which it will do, but distinct materials are cleaner.
- `Mat_Separator_Steel` must be distinct from `Mat_Shell_Steel` even though they
  look identical, because they are driven by different temperatures.

---

## 6. `Carbon_Bin_Fill` specifics

A simple box or cylinder representing the carbon level inside the bin.

- Its **origin must sit at the bottom face**, not the centre, so `scale.y` from 0
  to 1 grows it upward from the bin floor. A centre origin will grow it through the
  bin floor in both directions.
- At `scale.y = 1` it fills the bin to a plausible full level.
- Initial `scale.y` in the exported file: `0.0`.

This is a small detail that is annoying to fix after the fact, because it requires
re-exporting.

---

## 7. Validation checklist

Run before delivering the file. Cursor should also implement an automated version
as `frontend/scripts/validate-gltf.ts`, run in CI, which loads the glb and asserts
every name in section 4 is present.

**In Blender:**

- [ ] Every node name matches section 4 exactly, no `.001` suffixes
- [ ] Every material name matches section 5 exactly
- [ ] All `emissive` values are black
- [ ] `Door_Hinge` rotated 100 degrees on Y swings the door correctly
- [ ] `Discharge_Chute_Hinge` rotated on X opens the chute correctly
- [ ] `Carbon_Bin_Fill` origin is at its bottom face, `scale.y = 0`
- [ ] No negative scale anywhere, `Object > Apply > All Transforms` done
- [ ] Triangle count under 50,000 (Statistics overlay)
- [ ] World origin is at the vessel base centre, on the ground
- [ ] No animation data, no cameras, no lights
- [ ] `Pipe_N2_Line` is geometrically separate from the gas piping
- [ ] All normals outward, `Mesh > Normals > Recalculate Outside`

**After export:**

- [ ] Loads in https://gltf-viewer.donmccurdy.com without warnings
- [ ] Y is up, the reactor stands upright
- [ ] File under 8 MB
- [ ] `validate-gltf.ts` passes

---

## 8. Delivery in stages, so nothing blocks

Do not wait for a finished model. Deliver in three passes.

**Pass 1, day one or two, blockout.** Correct names, correct hierarchy, correct
pivots, primitive shapes only. Cylinders and boxes, no detail, no textures. This
unblocks and validates all the scene code immediately, and it is maybe two hours of
work. **This pass is worth more to the project than the finished model**, because it
converts the asset from a blocker into an upgrade.

**Pass 2, day three or four, modelled.** Real geometry, correct proportions,
piping routed properly, materials assigned. Still untextured or with flat colours.
Good enough to demo.

**Pass 3, day five or six, finished.** Baked textures, wear, weld seams, labels,
grime. Purely visual polish, no structural change, so it cannot break anything.

If pass 3 does not happen, the project still ships on pass 2. If pass 1 is late,
everything downstream slips. Prioritise accordingly.

---

## 9. If the model is outsourced

Send this document verbatim, plus reference photographs of the actual reactors at
the plant. Emphasise three things, because these are what a generalist 3D artist
will get wrong:

1. **Node names are a code interface.** Renaming anything, however sensible the new
   name, breaks the application. This is unlike most 3D work and needs saying explicitly.
2. **Pivots carry meaning.** `Door_Hinge` must be a real hinge axis, not a
   convenient centre point.
3. **No baked lighting, no emissive, no animation.** All of that is code-driven.

Ask for pass 1 as a separate, quick, paid deliverable up front. It is the highest
value item and it is cheap.

Also get the plant to confirm the model matches the real vessel layout, especially
where the gas passage runs and where the discharge chute sits. A digital shadow whose
geometry does not match the plant undermines the credibility of everything else on
screen, and an operator will spot it in seconds.
