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
    model_version: "excel-seed-v1",
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
  type Row = {
    machine_id: number;
    oil_yield_pct: number | null;
    carbon_yield_pct: number | null;
    steel_yield_pct: number | null;
    total_duration_min: number | null;
    feed_mass_kg: number | null;
    moisture_pct: number | null;
  };
  const history = (plantBatches as { batches: Row[] }).batches.filter((b) => b.machine_id === mid);
  const avg = (key: keyof Row, fallback: number) => {
    const vals = history.map((b) => b[key]).filter((v): v is number => typeof v === "number");
    if (!vals.length) return fallback;
    return vals.reduce((a, b) => a + b, 0) / vals.length;
  };
  const baseOil = avg("oil_yield_pct", 40);
  const baseCarbon = avg("carbon_yield_pct", 33);
  const baseSteel = avg("steel_yield_pct", 12);
  const baseTime = avg("total_duration_min", 2000);
  const baseFeed = avg("feed_mass_kg", 10500);
  const moistKg = avg("moisture_pct", 600);
  const moistPct = baseFeed > 0 ? (moistKg / baseFeed) * 100 : 6;
  const oil = Math.max(28, Math.min(52, baseOil - (moisture - moistPct) * 0.8 + ((feed - baseFeed) / baseFeed) * 2));
  const carbon = Math.max(20, Math.min(40, baseCarbon - (peak - 450) * 0.02));
  const steel = Math.max(8, Math.min(18, baseSteel + (moisture - moistPct) * 0.1));
  const duration = Math.round(baseTime + (feed - baseFeed) * 0.05 + (moisture - moistPct) * 15 + (peak - 450) * 0.8);
  const warnings: string[] = [];
  if (feed < 4500 || feed > 14000) warnings.push("Feed mass is outside the usual plant-log range.");
  if (moisture < 1 || moisture > 12) warnings.push("Moisture is outside the usual plant-log range.");
  if (peak < 400 || peak > 500) warnings.push("Peak Tr is outside the usual demo range.");
  if (feed < 9500 || feed > 12900 || moisture > 11 || moisture < 3) {
    warnings.push("Outside typical history — treat as a rough guide.");
  }
  const label = mid === 1093 ? "R1" : mid === 1094 ? "R2" : "R3";
  return {
    input_echo: body,
    model_version: "excel-seed-v1",
    predicted_total_duration_min: duration,
    extrapolation_warnings: [
      `${label} estimate anchored on ${history.length} plant log batches (Excel seed).`,
      ...warnings,
    ],
    phases: [
      { process_state: "heating", duration_min: Math.round(duration * 0.35) },
      { process_state: "holding", duration_min: Math.round(duration * 0.4) },
      { process_state: "cooling", duration_min: Math.round(duration * 0.25) },
    ],
    predicted_yields: {
      oil_yield_pct: { p10: oil - 3, p50: oil, p90: oil + 3 },
      carbon_yield_pct: { p10: carbon - 2, p50: carbon, p90: carbon + 2 },
      steel_yield_pct: { p10: steel - 1, p50: steel, p90: steel + 1 },
    },
  };
}

export function demoBriefing() {
  const n = (plantBatches as { n_batches?: number }).n_batches ?? 0;
  return {
    generated_at: new Date().toISOString(),
    plant: "Plant Floor",
    reactors: [
      { id: "R1", state: "heating", tr_c: 318, note: "Mid-ramp, batch ~3h in" },
      { id: "R2", state: "holding", tr_c: 412, note: "Near peak hold" },
      { id: "R3", state: "cooling", tr_c: 265, note: "Cooldown-down after hold" },
    ],
    coverage_note: `Floor live view is demo telemetry; Batches/What-if use ${n} anonymized Excel plant-log rows.`,
  };
}

export function demoInsights() {
  const key = process.env.HTPP_ANTHROPIC_API_KEY || process.env.ANTHROPIC_API_KEY || "";
  const wid = process.env.HTPP_ANTHROPIC_WORKSPACE_ID || process.env.ANTHROPIC_WORKSPACE_ID || "";
  const n = (plantBatches as { n_batches?: number }).n_batches ?? 0;
  return {
    insights: [
      {
        severity: "info",
        title: `${n} plant-log batches loaded`,
        detail: "Batches come from the anonymized Excel mass log (feed, moisture, oil/carbon/steel, time).",
      },
      {
        severity: "warning",
        title: "Floor is still demo live view",
        detail: "3D floor uses seeded telemetry. Growing history needs DuckDB/DB — Vercel does not append new Excel rows automatically.",
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
  const all = (plantBatches as { batches: Array<{ machine_id: number; log_date: string }> }).batches;
  const per_machine = MACHINE_IDS.map((id, slot) => {
    const mine = all.filter((b) => b.machine_id === id);
    const daily = Array.from({ length: days }, (_, i) => {
      const d = new Date(start);
      d.setUTCDate(start.getUTCDate() + i);
      const date = d.toISOString().slice(0, 10);
      const hits = mine.filter((b) => b.log_date === date).length;
      return {
        date,
        n_samples: hits > 0 ? hits * 300 : 0,
        median_interval_s: 240,
        max_gap_s: hits > 0 ? 480 : 3600,
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
      history_floor: mine[0]?.log_date ?? daily[0]?.date ?? null,
      last_sample_at: new Date().toISOString(),
      n_samples: mine.length,
      median_interval_s: 240,
      daily,
      gaps,
    };
  });
  return {
    per_machine,
    batches: {
      total: all.length,
      complete: all.length,
      usable_for_training: all.length,
      with_excel_log: all.length,
      with_fault: 0,
    },
    excel: { rows_parsed: all.length, rows_unmatched: 0, unmatched_detail: [], closure_error_pct: {} },
    unmapped_process_values: [],
    ingest_failures: [],
  };
}

export const ASSISTANT_SYSTEM = `You are the HTPP Digital Shadow assistant for industrial batch reactors (Plant Floor: R1 Unit 1, R2 Unit 2, R3 Unit 3).

Rules:
- You only advise. You cannot actuate valves, change setpoints, or write to the panel.
- Use ONLY the plant briefing JSON and the user's question. If a number is missing, say so.
- Write for plant operators in plain English. Markdown bullets OK.
- Never invent or reveal customer, site, operator, email, password, or API credentials.
- Keep answers short: 2–6 sentences or a tight bullet list.
- Batch history may come from an anonymized Excel plant log on Vercel; say so if asked whether Floor is live PLC.`;
