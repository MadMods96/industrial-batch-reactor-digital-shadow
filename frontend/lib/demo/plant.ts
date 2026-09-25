/** Demo / seed plant payload for Vercel-only deploys (no external FastAPI). */

import plantBatches from "./plant_batches.json";

export const MACHINE_IDS = [1093, 1094, 1146] as const;

const LABELS: Record<number, string> = {
  1093: "R1 Unit 1",
  1094: "R2 Unit 2",
  1146: "R3 Unit 3",
};

const STATES = ["heating", "holding", "cooling"] as const;

function dense(tr0: number, state: string) {
  const n = 120;
  const trC: number[] = [];
  const tsC: number[] = [];
  const prBar: number[] = [];
  const psBar: number[] = [];
  const processState: string[] = [];
  for (let i = 0; i < n; i++) {
    const t = i / (n - 1);
    let tr = tr0;
    if (state === "heating") tr = tr0 + t * 40;
    else if (state === "cooling") tr = tr0 - t * 25;
    trC.push(Math.round(tr * 10) / 10);
    tsC.push(Math.round((tr * 0.55 + 40) * 10) / 10);
    prBar.push(Math.round((0.4 + t * 0.8) * 100) / 100);
    psBar.push(Math.round((0.2 + t * 0.3) * 100) / 100);
    processState.push(state);
  }
  return { step_s: 1, horizon_s: n, tr_c: trC, ts_c: tsC, pr_bar: prBar, ps_bar: psBar, process_state: processState };
}

export function liveSnapshot() {
  const now = new Date().toISOString();
  const machines = MACHINE_IDS.map((id, slot) => {
    const state = STATES[slot];
    const tr = [318, 412, 265][slot];
    return {
      machine_id: id,
      display_name: LABELS[id],
      scene_slot: slot,
      online: true,
      last_sample_at: now,
      staleness_s: 90 + slot * 20,
      batch_no: 40 + slot,
      batch_elapsed_min: [180, 260, 95][slot],
      process_state: state,
      process_raw: state,
      fault_state: "none",
      phase_elapsed_min: [40, 70, 25][slot],
      measured: {
        tr_c: tr,
        ts_c: Math.round(tr * 0.55 + 40),
        pr_bar: [0.9, 1.4, 0.5][slot],
        ps_bar: [0.3, 0.5, 0.2][slot],
        amb_temp_c: 29,
        roh_c_per_min: state === "heating" ? 1.2 : state === "cooling" ? -0.8 : 0.1,
      },
      interpolation_mode: "linear_fallback",
      dense: dense(tr, state),
      residual: { r_t_c: 0, r_t_norm: 0, r_p_bar: 0, ewma_z: 0, cusum: 0, alarm: false, severity: "ok" },
      projection: {
        predicted_end_at: null,
        predicted_total_duration_min: [420, 480, 400][slot],
        predicted_yields: {
          oil_yield_pct: { p10: 38, p50: 42, p90: 46 },
        },
      },
    };
  });
  return {
    type: "snapshot",
    server_time: now,
    model_version: "vercel-demo-v1",
    machines,
  };
}

export function demoBatches() {
  return {
    batches: (plantBatches as { batches: unknown[] }).batches,
    source: (plantBatches as { source?: string }).source,
    n_batches: (plantBatches as { n_batches?: number }).n_batches,
  };
}

export function demoReplay(key: string) {
  const machineId = Number(key.split("-")[0]) || 1093;
  const snap = liveSnapshot().machines.find((m) => m.machine_id === machineId) || liveSnapshot().machines[0];
  return {
    batch_key: key,
    machine_id: machineId,
    samples: snap.dense.tr_c.map((tr, i) => ({
      sampled_at: new Date(Date.now() - (120 - i) * 60_000).toISOString(),
      tr_c: tr,
      ts_c: snap.dense.ts_c[i],
      pr_bar: snap.dense.pr_bar[i],
      ps_bar: snap.dense.ps_bar[i],
      process_state: snap.dense.process_state[i],
    })),
  };
}

export function demoTelemetry(machineId: number) {
  const snap = liveSnapshot().machines.find((m) => m.machine_id === machineId) || liveSnapshot().machines[0];
  return {
    machine_id: machineId,
    samples: snap.dense.tr_c.map((tr, i) => ({
      sampled_at: new Date(Date.now() - (120 - i) * 240_000).toISOString(),
      tr_c: tr,
      ts_c: snap.dense.ts_c[i],
      pr_bar: snap.dense.pr_bar[i],
      ps_bar: snap.dense.ps_bar[i],
      process_raw: snap.dense.process_state[i],
      process_state: snap.dense.process_state[i],
      fault_state: "none",
    })),
  };
}

export function demoSimulate(body: {
  feed_mass_kg: number;
  moisture_pct: number;
  target_peak_tr_c: number;
  machine_id?: number;
}) {
  const feed = body.feed_mass_kg;
  const moisture = body.moisture_pct;
  const peak = body.target_peak_tr_c;
  const mid = body.machine_id ?? 1093;
  // Per-reactor bias so side-by-side compare is not identical in demo mode.
  const bias =
    mid === 1093 ? { oil: 0, carbon: 0.4, steel: -0.2, time: 0, heat: "R1 tends slightly slower to peak." }
    : mid === 1094 ? { oil: 1.2, carbon: -0.6, steel: 0.1, time: -18, note: "R2 usually clearer oil cut in plant logs." }
    : { oil: -0.8, carbon: 0.8, steel: 0.4, time: 12, note: "R3 often longer cool-down in demo history." };

  const oil = Math.max(28, Math.min(52, 48 - moisture * 1.1 + (feed - 10000) * 0.0004 + bias.oil));
  const carbon = Math.max(20, Math.min(40, 35 - (peak - 450) * 0.02 + bias.carbon));
  const steel = Math.max(8, Math.min(18, 12 + moisture * 0.2 + bias.steel));
  const duration = Math.round(360 + feed / 80 + moisture * 8 + (peak - 430) * 0.4 + bias.time);
  const warnings: string[] = [];
  if (feed < 4500 || feed > 14000) warnings.push("Feed mass is outside the usual demo range.");
  if (moisture < 1 || moisture > 12) warnings.push("Moisture is outside the usual demo range.");
  if (peak < 400 || peak > 500) warnings.push("Peak Tr is outside the usual demo range.");
  // Soft nudge when inputs sit near edge of logged band shown in the UI copy.
  if (feed < 9500 || feed > 12900 || moisture > 11 || moisture < 3) {
    warnings.push("Outside typical history — treat as a rough guide.");
  }
  return {
    input_echo: body,
    model_version: "vercel-demo-v1",
    predicted_total_duration_min: duration,
    extrapolation_warnings: [
      `Vercel demo estimate for ${mid === 1093 ? "R1" : mid === 1094 ? "R2" : "R3"}. ${bias.note}`,
      ...warnings,
    ],
    phases: [
      { process_state: "heating", duration_min: Math.round(duration * (mid === 1094 ? 0.32 : 0.35)) },
      { process_state: "holding", duration_min: Math.round(duration * (mid === 1094 ? 0.43 : 0.4)) },
      { process_state: "cooling", duration_min: Math.round(duration * (mid === 1146 ? 0.28 : 0.25)) },
    ],
    predicted_yields: {
      oil_yield_pct: { p10: oil - 3, p50: oil, p90: oil + 3 },
      carbon_yield_pct: { p10: carbon - 2, p50: carbon, p90: carbon + 2 },
      steel_yield_pct: { p10: steel - 1, p50: steel, p90: steel + 1 },
    },
  };
}

export function demoBriefing() {
  return {
    generated_at: new Date().toISOString(),
    plant: "Plant Floor",
    reactors: [
      { id: "R1", state: "heating", tr_c: 318, note: "Mid-ramp, batch ~3h in" },
      { id: "R2", state: "holding", tr_c: 412, note: "Near peak hold" },
      { id: "R3", state: "cooling", tr_c: 265, note: "Cooldown-down after hold" },
    ],
    coverage_note: "Demo dataset on Vercel — not live panel telemetry.",
  };
}

export function demoInsights() {
  const key = process.env.HTPP_ANTHROPIC_API_KEY || process.env.ANTHROPIC_API_KEY || "";
  const wid = process.env.HTPP_ANTHROPIC_WORKSPACE_ID || process.env.ANTHROPIC_WORKSPACE_ID || "";
  return {
    insights: [
      {
        severity: "info",
        title: "R2 is holding near peak",
        detail: "Demo signal: Unit 2 looks stable around 412 °C. Watch pressure if hold runs long.",
      },
      {
        severity: "warning",
        title: "Demo mode on Vercel",
        detail: "Floor data is a seeded digital-shadow demo (not live PLC). Claude still works if API keys are set.",
      },
    ],
    claude_configured: Boolean(key.trim()) && Boolean(wid.trim()),
    claude_needs_workspace: Boolean(key.trim()) && !Boolean(wid.trim()),
    generated_at: new Date().toISOString(),
  };
}

export function demoCoverage() {
  const days = 28;
  const start = new Date();
  start.setUTCDate(start.getUTCDate() - (days - 1));
  const per_machine = MACHINE_IDS.map((id, slot) => {
    const daily = Array.from({ length: days }, (_, i) => {
      const d = new Date(start);
      d.setUTCDate(start.getUTCDate() + i);
      const gapDay = i % (7 + slot) === 3;
      return {
        date: d.toISOString().slice(0, 10),
        n_samples: gapDay ? 0 : 320 + ((i + slot * 3) % 40),
        median_interval_s: 240,
        max_gap_s: gapDay ? 3600 : 480,
      };
    });
    const gaps = daily
      .filter((row) => row.n_samples === 0)
      .map((row) => ({
        from: `${row.date}T00:00:00Z`,
        to: `${row.date}T01:00:00Z`,
        duration_s: 3600,
      }));
    return {
      machine_id: id,
      history_floor: daily[0]?.date ?? null,
      last_sample_at: new Date().toISOString(),
      n_samples: [12919, 13014, 13112][slot],
      median_interval_s: 240,
      daily,
      gaps,
    };
  });
  return {
    per_machine,
    batches: {
      total: 9,
      complete: 8,
      usable_for_training: 7,
      with_excel_log: 6,
      with_fault: 1,
    },
    excel: { rows_parsed: 24, rows_unmatched: 2, unmatched_detail: [], closure_error_pct: {} },
    unmapped_process_values: [],
    ingest_failures: Array.from({ length: 7 }, (_, i) => ({
      at: new Date(Date.now() - i * 86_400_000).toISOString(),
      status: "demo_note",
      detail: "Vercel demo — no live panel pull",
    })),
  };
}

export const ASSISTANT_SYSTEM = `You are the HTPP Digital Shadow assistant for industrial batch reactors (Plant Floor: R1 Unit 1, R2 Unit 2, R3 Unit 3).

Rules:
- You only advise. You cannot actuate valves, change setpoints, or write to the panel.
- Use ONLY the plant briefing JSON and the user's question. If a number is missing, say so.
- Write for plant operators in plain English. Markdown bullets OK.
- Never invent or reveal customer, site, operator, email, password, or API credentials.
- Keep answers short: 2–6 sentences or a tight bullet list.
- This may be demo data on Vercel; say so if asked whether it is live PLC.`;
