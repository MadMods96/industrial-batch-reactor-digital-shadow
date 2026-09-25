# 05 - Modelling Spec

## 0. The governing constraint

Heat input is **not measured.** There is no fuel flow meter, no burner firing rate,
no electricity meter. There is one temperature sensor per vessel and a
4-minute sample interval.

Every modelling decision below follows from that. The strategy is to identify what
the data *can* support, in a deliberate order, and to be explicit in the paper
about which parameters are physical and which are effective lumped quantities.

Order of identification, and this order matters:

1. **Cooling phase first.** Heat input is zero, so the thermal parameters are
   identifiable from an unforced decay. This is the only clean identification in
   the whole project. Everything else is anchored to it.
2. **Heating phase second**, using the cooling-derived time constant to break the
   otherwise unidentifiable product of heat input and capacitance.
3. **Gas phase third**, where the deviation from the thermal model *is* the
   reaction signal.
4. **Yield model last**, on features derived from the three above.

Never fit heating before cooling. The heating phase alone gives you the ratio
`Q_in/UA` and the time constant `C/UA` but not `Q_in`, `UA` and `C` separately.

---

## M1. Reduced-order thermal model

### Governing equation

Single lumped zone for the reactor vessel plus charge:

```
C_eff · dTr/dt  =  Q_in(t)  -  UA_eff · (Tr - T_amb)  -  Q_rxn(t)
```

| Symbol | Meaning | Unit | Identifiable? |
|---|---|---|---|
| `C_eff` | Effective thermal capacitance, shell plus charge | J/K | From cooling, up to a scale shared with UA |
| `Q_in` | Effective heat input | W | Heating phase only, given tau |
| `UA_eff` | Overall loss coefficient | W/K | From cooling |
| `Q_rxn` | Net endothermic reaction heat | W | Not directly. Inferred as a residual |
| `T_amb` | Ambient, **measured** as `amb_temp_c` | degC | measured |

Define the time constant:

```
tau = C_eff / UA_eff        [s]
```

**Use `amb_temp_c` from the data. Do not assume 25 degC.** Ambient was 28.5 degC
at the time of inspection and an Indian plant will swing a long way seasonally.
Assuming a constant ambient injects a systematic bias directly into `UA_eff`.

### M1.1 Cooling-phase identification (RQ1, do this first)

During `process_state = cooling`, set `Q_in = 0` and `Q_rxn ≈ 0`. The equation
integrates to:

```
Tr(t) = T_amb + (Tr_0 - T_amb) · exp(-t / tau_cool)
```

Fit per batch per machine on the cooling segment:

```python
def fit_cooling_tau(t_s, tr_c, amb_c) -> CoolingFit:
    """
    Nonlinear least squares for tau_cool and Tr_0.

    t_s   : seconds since cooling phase start, from ACTUAL timestamps
    amb_c : use the segment mean; if it drifts more than 3 degC across the
            segment, integrate numerically instead of using the closed form.

    Returns tau_cool_min, tr0_c, r_squared, rmse_c, n_points, converged.
    """
```

Implementation requirements:

- `scipy.optimize.curve_fit` with bounds `tau_cool in [1, 2000] min`, and
  `p0` from a log-linear pre-fit of `log(Tr - T_amb)` against `t`, which is
  cheap and makes convergence reliable.
- **Never assume uniform `dt`.** Build `t_s` from real timestamps.
- Require at least 8 points in the segment. Below that, record
  `converged = False` and skip. A 4 h 16 min cooling phase at ~4 min gives about
  64 points, so this is comfortable in normal operation.
- Discard fits with `r_squared < 0.9` and count them. A cooling phase that is not
  a clean exponential means something else was happening, and that is a finding.
- Report the distribution of `tau_cool_min` per machine: median, IQR,
  coefficient of variation.

**This is the RQ1 result.** Success criterion from the PRD: CV within a machine
below 0.3. If CV is high, report it honestly and investigate whether it correlates
with `feed_mass_kg`, which it physically should, since charge mass enters `C_eff`.
That correlation, if present, is a genuinely nice result: it means the model can
infer charge mass from the cooling curve alone.

### M1.2 Separating UA from C

`tau_cool` gives the ratio only. To split it, use the physical decomposition:

```
C_eff = C_shell + m_charge · cp_charge
```

`C_shell` is a constant per machine. `m_charge` is `feed_mass_kg` from the Excel.
So regress the identified `tau_cool` across batches:

```
tau_cool · UA_eff = C_shell + feed_mass_kg · cp_charge
```

With `UA_eff` treated as constant per machine, a linear regression of `tau_cool`
against `feed_mass_kg` yields `C_shell/UA_eff` as intercept and
`cp_charge/UA_eff` as slope. Fix `cp_charge` to a literature value for shredded
tyre rubber (approximately 1.9 kJ/(kg·K), **cite the source, do not use this
number on my authority**) and `UA_eff`, `C_shell` both fall out in absolute terms.

State clearly in the paper that `cp_charge` is assumed from literature, not
identified. That is a legitimate and common move, but it must be declared.

### M1.3 Heating-phase identification

During `process_state = heating`, assume `Q_in = Q_H` constant and `Q_rxn ≈ 0`
(devolatilisation has not started in earnest below roughly 300 degC, which needs
verification against the `gas` phase onset temperature in the data):

```
Tr(t) = T_amb + (Q_H/UA_eff)·(1 - exp(-t/tau_h)) + (Tr_0 - T_amb)·exp(-t/tau_h)
```

Fit `Q_H` and `tau_h`, with `tau_h` initialised from `tau_cool` and bounded to
within a factor of three of it. A heating time constant wildly different from the
cooling one signals that the constant-`Q_in` assumption has failed, which itself
is worth reporting.

The 1 h 43 min heating phase seen on batch 833 gives about 26 points at 4-minute
cadence. Two parameters from 26 points is fine. Do not add a third.

**Cross-validate against the panel's own `roh_c_per_min`.** The panel reports rate
of heating directly. Compare the model's `dTr/dt` against it. Close agreement
validates both. Divergence tells you either the panel computes ROH over a
different window, or the fit is poor. Either way it is information, so build the
comparison plot.

### M1.4 Gas-phase reaction signal, the good idea

During `gas`, hold `UA_eff` and `C_eff` at their identified values, hold `Q_in` at
the heating-phase `Q_H` (assumption: burner setting unchanged; verify against
`roh_c_per_min` behaviour), and solve for the residual term:

```
Q_rxn(t) = Q_in - UA_eff·(Tr - T_amb) - C_eff · dTr/dt
```

Then integrate:

```
E_rxn = ∫ Q_rxn(t) dt        [J]  over the gas phase
```

`E_rxn` is a data-derived estimate of total reaction enthalpy, and it should scale
with the mass actually devolatilised, which means it should scale with
`oil_mass_kg + gas_mass_kg`. **Test that correlation.** If it holds, it is the
strongest physical result in the paper: a purely thermal measurement predicting
mass yield.

Compute `dTr/dt` with a Savitzky-Golay filter (window 5 samples, polyorder 2) on
the irregular grid, not a raw finite difference. At 4-minute cadence with integer-ish
temperature readings, a raw difference is almost entirely quantisation noise.

**Note the quantisation.** Observed `tr_c` values are integers (26, 34, 193, 195).
A 1 degC quantum over a 4-minute interval is 0.25 degC/min of pure noise floor in
any derivative. Report this as a stated limitation and let it justify the smoothing
and the refusal to model fast dynamics.

---

## M2. Conversion kinetics

### Single-step global model

```
dα/dt = k0 · exp(-Ea / (R · Tr_K)) · (1 - α)^n
```

`α` is conversion from 0 to 1, `Tr_K = tr_c + 273.15`, `R = 8.314 J/(mol·K)`.

Start with `n = 1`. Fit `k0`, `Ea` and then `n` only if `n = 1` is clearly
inadequate and there are enough batches to justify a third parameter.

### Fitting strategy

There is no measured `α(t)`. Only the endpoint is observable, through the Excel
yields. So fit indirectly:

1. For each usable batch, integrate the ODE over the measured `Tr(t)` history with
   `scipy.integrate.solve_ivp` (method `Radau`, the problem is stiff at high
   temperature) to get `alpha_final`.
2. Choose `k0` and `Ea` to maximise the correlation between `alpha_final` and the
   measured volatile yield `(oil_yield_pct + gas_yield_pct)`, or `oil_yield_pct`
   alone where gas is unmeasured.
3. Objective: minimise the residual of a **linear** fit of measured volatile yield
   against `alpha_final`. A linear rather than identity relationship is correct,
   because `alpha_final` is dimensionless conversion and the yield percentage
   depends on feedstock volatile content too.
4. Constrain `Ea` to a physically plausible band for tyre pyrolysis and **cite the
   band from literature.** Typical reported values sit in the low hundreds of
   kJ/mol, but get the actual range from a real reference and quote it. Do not
   invent bounds.
5. If the correlation is weak, report that honestly. It means 4-minute temperature
   history does not determine conversion, which is a legitimate negative result
   and useful to the field.

### Guard against overclaiming

A single-step model with two fitted parameters against roughly 100 endpoint
observations, where the parameters were chosen to maximise correlation with the
target, is at serious risk of looking better than it is. Therefore:

- Fit `k0` and `Ea` on the **training split only.** Never on all batches.
- Report `alpha_final` versus measured yield on the **held-out split.**
- Call it a "lumped conversion index" in the paper if the physical interpretation
  is weak. Do not claim to have measured tyre pyrolysis kinetics from a plant
  thermocouple. That claim would not survive review.

---

## M3. Yield prediction

### Targets

`oil_yield_pct`, `carbon_yield_pct`, `steel_yield_pct`. Three separate models.

`steel_yield_pct` is a special case worth noting: steel content is a property of
the **feedstock**, essentially independent of process conditions. So the thermal
features should have almost **no** predictive power for steel, while feedstock
type should have nearly all of it. **This is your negative control.** If the model
"predicts" steel yield from peak temperature, you have a leakage bug. Build this
check in explicitly; it is the cheapest sanity test available and it will catch
mistakes the others miss.

### Features

Three blocks, and the ablation across them is a result in itself.

**Block A, feedstock only (the baseline to beat):**
`feed_mass_kg`, `moisture_pct`, `feedstock_type` (one-hot)

**Block B, thermal severity:**
`peak_tr_c`, `time_above_350c_min`, `time_above_400c_min`, `time_above_450c_min`,
`severity_index_c_min`, `mean_roh_heating_c_per_min`, `max_roh_c_per_min`,
`heating_duration_min`, `gas_duration_min`, `mean_amb_temp_c`

**Block C, model-derived:**
`tau_cool_min`, `ua_eff_w_per_k`, `c_eff_j_per_k`, `q_in_heating_w`,
`alpha_final`, `e_rxn_j`

**Block D, pressure:**
`max_pr_bar`, `mean_pr_gas_bar`, `pr_oscillation_count`, `pr_integral_bar_min`

Severity index, the headline engineered feature:

```
severity_index_c_min = ∫ max(0, Tr(t) - T_ref) dt,   T_ref = 350 degC
```

Integrate with the trapezoid rule on real timestamps. Sweep `T_ref` over 300, 350,
400 and 450 and keep whichever correlates best with oil yield **on the training
split only**, then report the sweep. Selecting `T_ref` on all data is leakage.

### Models, in order of preference

1. **Ridge regression.** Standardise features. Tune `alpha` by nested CV. This is
   the primary model and it should be the headline result unless something else
   clearly beats it.
2. **ElasticNet.** For feature selection and a sparser, more interpretable story.
3. **Gradient boosting** (`HistGradientBoostingRegressor`, `max_depth=3`,
   `max_iter` tuned by early stopping). Comparison only.

**No neural networks.** With about 100 batches this would be indefensible, and a
reviewer will say so. State the sample size as the reason in the paper.

### Baselines, mandatory

Beating nothing is not a result. Report against:

- **B0, global mean.** Predict the training-set mean yield for everything.
- **B1, feed mass only.** Univariate linear regression on `feed_mass_kg`.
- **B2, Block A only.** Feedstock features, no process information at all.

**RQ2 is answered yes only if Block A+B+C beats B2 on held-out data by more than
B2's own standard error.** Anything less is not a demonstrated improvement, and
saying otherwise would be dishonest.

### Prediction intervals

Required, because the UI shows them and a point estimate on 100 samples is
overconfident.

Primary method: **quantile regression** at the 10th, 50th and 90th percentiles
(`GradientBoostingRegressor(loss="quantile")`), or conformal prediction over the
Ridge model, which is cleaner and gives coverage guarantees. Prefer conformal if
time allows.

Report empirical coverage on the held-out split. If the nominal 80 percent
interval covers 55 percent of held-out points, say so.

### Validation protocol

- **Time-based split.** Train on the earliest 70 percent of batches by
  `started_at`, validate on the next 15 percent, test on the final 15 percent.
  **Never random split.** Reactor condition drifts, and a random split leaks the
  future into the past.
- Report `GroupKFold` grouped by `machine_id` as well, which answers whether the
  model transfers across reactors. That is the more interesting question for
  industrial deployment.
- Metrics: MAE, RMSE, R², MAPE, all in yield percentage points. Report MAE in
  percentage points as the headline because it is interpretable to a plant
  operator.
- Report the **number of batches** in every split, in every table. With this sample
  size, n must appear next to every metric.

---

## M4. Fault detection (RQ3, the strongest contribution)

### Ground truth, already in the data

The panel labels faults itself: `Choke Emergency`, `Gas Passage Choke`,
`Pressure Sensor Error`. Each labelled occurrence gives a timestamp
`t_panel_alarm`. Labelled industrial fault data is rare and this is the project's
best asset.

### Detector

Residuals from the fitted thermal model, computed on the phase-appropriate model:

```
r_T(t) = Tr_measured(t) - Tr_model(t)
r_P(t) = Pr_measured(t) - Pr_model(t)
```

Normalise each by the training-set residual standard deviation for that phase, so
thresholds are comparable across phases. Then run two detectors and compare them:

**EWMA:**
```
z(t) = λ·r_norm(t) + (1-λ)·z(t-1),      λ = 0.3
alarm when |z(t)| > h        for tuned h
```

**CUSUM, two-sided:**
```
S+(t) = max(0, S+(t-1) + r_norm(t) - k)
S-(t) = max(0, S-(t-1) - r_norm(t) - k)
alarm when max(S+, S-) > h,   k = 0.5, h tuned
```

CUSUM is better at slow drifts, which is what a developing choke should look like.
EWMA is better at steps. Report both; the comparison is a legitimate minor result.

Tune `h` on the training split by maximising F1 against the panel labels. Report
the full ROC and the precision-recall curve, since with heavily imbalanced fault
data a single threshold tells you little.

### The headline metric: detection lead time

```
lead_time_min = t_panel_alarm - t_detector_alarm
```

Positive means the model saw it first. Report the **median and IQR across all
labelled fault events**, not the mean, since the distribution will be skewed and
one long lead time should not carry the result.

Be rigorous about what counts:

- An alarm fired more than 120 minutes before the panel alarm, with nothing
  anomalous in between, is probably a false positive, not a heroic early warning.
  Define a matching window (suggest 120 min) up front, before looking at results,
  and state it.
- Detector alarms with no panel alarm inside the window are **false positives.**
  Count them. Report the false alarm rate per batch, because a detector that fires
  constantly will always have great lead time and be useless in a plant.
- Panel alarms with no detector alarm are **misses.** Count them.
- **Resolution floor: 4 minutes.** Lead time cannot be measured more finely than
  the sample interval. A median lead time of 8 minutes means two samples. Say this
  explicitly; do not report lead time to a decimal place.

### Honest failure mode

`Pressure Sensor Error` is a **sensor** fault, not a **process** fault. A thermal
residual detector has no physical reason to anticipate it. Either exclude it from
the lead-time analysis with a stated reason, or report it separately and expect
near-zero lead time. Lumping it in with process faults would inflate the event
count and muddy the result.

---

## M5. Simulation and live projection

### Forward rollout

```python
def simulate_batch(
    feed_mass_kg: float,
    moisture_pct: float,
    feedstock_type: str,
    machine_id: int,
    target_peak_tr_c: float,
    heating_power_scale: float = 1.0,   # multiplier on fitted Q_H
) -> SimulationResult
```

Procedure:

1. Look up that machine's fitted `UA_eff`, `C_shell`, `Q_H` distribution.
2. Compute `C_eff = C_shell + feed_mass_kg · cp_charge`.
3. Integrate the thermal ODE with `Q_in = Q_H · heating_power_scale` until
   `target_peak_tr_c`, then through gas, then `Q_in = 0` for cooling.
4. Phase transitions: predict durations from the fitted regressions on the
   simulated trajectory, not from hardcoded constants.
5. Integrate the kinetics ODE alongside to get `alpha_final`.
6. Compute severity features from the simulated trajectory and feed them to the
   yield models to get predicted yields with intervals.
7. Return dense `Tr(t)`, `Ts(t)`, `Pr(t)`, phase boundaries, total duration,
   predicted yields with intervals.

`Ts` and `Pr` do not have first-principles models here. Fit simple empirical
relations from data: `Ts` as a lagged first-order response to `Tr`, `Pr` as a
function of `Tr` and the gas-phase conversion rate. **Label these as empirical
correlations, not physics, in the paper.** They exist to make the 3D scene move
plausibly and to support what-if exploration, not to make physical claims.

### Replay validation

For each held-out batch, run `simulate_batch` with that batch's actual feed mass,
moisture and feedstock, and compare against measured. Report trajectory RMSE in
degC, phase-duration errors in minutes, total-batch-time error in minutes, and
yield errors in percentage points. This is the most persuasive single figure in
the paper: simulated against actual on a batch the model never saw.

### Live projection

On each ingestion tick, for each machine with a running batch:

1. Take the measured current state.
2. Compute the residual against what was projected for the interval that just closed.
3. Update the fault detector with that residual.
4. Project forward from the measured state to the end of the batch.
5. Emit a **dense trajectory** for the next interval for the 3D scene, plus the
   remainder-of-batch projection, plus the residual and detector status.

**Re-anchor the projection on every real sample.** Never let it free-run, or errors
compound and the scene drifts away from reality over a 26-hour batch.

---

## M6. Model-based interpolation for the 3D scene

This is what makes the 3D scene honest rather than decorative. Read section 4 of
doc 02 first.

```python
def dense_trajectory(
    machine_id: int,
    anchor_state: TelemetrySample,
    horizon_s: float = 300.0,
    step_s: float = 1.0,
) -> DenseTrajectory
```

- Integrate the fitted thermal and empirical models forward from `anchor_state`
  at 1-second steps over a horizon slightly longer than the expected sample
  interval (300 s against a ~240 s cadence, so the scene never runs dry).
- Return arrays for `t_offset_s`, `tr_c`, `ts_c`, `pr_bar`, `ps_bar`, plus the
  predicted `process_state` if a phase transition is expected inside the horizon.
- The frontend plays this at display rate. On the next real sample the frontend
  blends from the projected value to the measured one over about 400 ms. See doc 07.

Constraints:

- **Monotonic and physically bounded.** Clamp `tr_c` to `[0, 900]` and reject a
  trajectory whose derivative exceeds a plausible `max_roh` by more than 3x. A
  diverging ODE solve must never reach the scene; fall back to holding the last
  value and log it.
- If no fitted model exists for a machine yet (before the first fit), fall back to
  linear interpolation and set `interpolation_mode = "linear_fallback"` in the
  payload. The HUD must display this, so the scene never silently implies model
  backing it does not have.
- `horizon_s` and `step_s` are configurable. 300 s at 1 s is 300 points per machine
  per tick, which is around 12 KB of JSON for three machines. Entirely acceptable
  every four minutes.

---

## M7. Artefacts and reproducibility

`registry.py` saves, per fit run:

```
artifacts/
  {timestamp}_{git_sha}/
    thermal_per_machine.json     # UA_eff, C_shell, Q_H distributions
    cooling_fits.parquet         # every per-batch tau fit with diagnostics
    kinetics.json                # k0, Ea, n, and the training split used
    yield_oil.joblib
    yield_carbon.joblib
    yield_steel.joblib
    fault_detector.json          # lambda, k, h, and tuning provenance
    empirical_ts_pr.json
    feature_spec.json            # exact feature list and order
    split_manifest.json          # every batch_key by split, for audit
    metrics.json                 # every number that appears in the paper
    LATEST -> symlink
```

Rules:

- **`split_manifest.json` is mandatory.** Every reported number must be traceable
  to exactly which batches produced it. This is what makes the result auditable.
- `feature_spec.json` pins feature order so inference cannot silently permute
  columns, which is a classic and invisible source of wrong predictions.
- `metrics.json` is the only source for tables in the paper. No hand-copied
  numbers, ever.
- The API loads `LATEST` and never refits at request time.
- `make reproduce` must regenerate everything from the database with no manual
  steps.
