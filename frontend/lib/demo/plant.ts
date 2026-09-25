/** Honest demo / Excel-seed payloads (Fix Brief 003). Never label this as live PLC. */

import plantBatches from "./plant_batches.json";

export const MACHINE_IDS = [1093, 1094, 1146] as const;
export const DEMO_MODE = true;

const LABELS: Record<number, string> = {
  1093: "R1 Unit 1",
  1094: "R2 Unit 2",
  1146: "R3 Unit 3",
};

/** Doc 03 vocabulary — never "holding". */
const STATES = ["heating", "gas", "cooling"] as const;

function denseHold(tr: number, ts: number, pr: number, ps: number, state: string) {
  const n = 300;
  const trC = Array.from({ length: n }, () => tr);
  const tsC = Array.from({ length: n }, () => ts);
  const prBar = Array.from({ length: n }, () => pr);
  const psBar = Array.from({ length: n }, () => ps);
  const processState = Array.from({ length: n }, () => state);
  return { step_s: 1, horizon_s: n, tr_c: trC, ts_c: tsC, pr_bar: prBar, ps_bar: psBar, process_state: processState };
}

export function liveSnapshot() {
  const now = new Date().toISOString();
  const machines = MACHINE_IDS.map((id, slot) => {
    const state = STATES[slot];
    const tr = [318, 412, 265][slot];
    const ts = Math.round(tr * 0.55 + 40);
    const pr = [0.9, 1.4, 0.5][slot];
    const ps = [0.3, 0.5, 0.2][slot];
    return {
      machine_id: id,
      display_name: LABELS[id],
      scene_slot: slot,
      online: false,
      last_sample_at: now,
      staleness_s: 86_400,
      batch_no: null,
      batch_elapsed_min: null,
      process_state: state,
      process_raw: state,
      fault_state: "none",
      phase_elapsed_min: null,
      measured: {
        tr_c: tr,
        ts_c: ts,
        pr_bar: pr,
        ps_bar: ps,
        amb_temp_c: 29,
        roh_c_per_min: null,
      },
      interpolation_mode: "linear_fallback",
      dense: denseHold(tr, ts, pr, ps, state),
      residual: null,
      projection: {
        predicted_end_at: null,
        predicted_total_duration_min: null,
        predicted_yields: null,
      },
    };
  });
  return {
    type: "snapshot",
    server_time: now,
    model_version: null,
    demo: true,
    label: "DEMO DATA — Excel seed / synthetic floor (not live panel)",
    machines,
  };
}

export function demoBatches() {
  return {
    batches: (plantBatches as { batches: unknown[] }).batches,
    source: (plantBatches as { source?: string }).source,
    note: (plantBatches as { note?: string }).note,
    n_batches: (plantBatches as { n_batches?: number }).n_batches,
  };
}

export function demoReplay(key: string) {
  const batches = (plantBatches as { batches: Array<Record<string, unknown>> }).batches;
  const batch = batches.find((b) => b.batch_key === key);
  if (!batch) {
    return {
      batch_key: key,
      mode: "missing",
      message: "Unknown batch key.",
      excel: null,
      t_offset_s: [],
      measured: { tr_c: [] },
      simulated: { tr_c: [] },
      process_state_measured: [],
      in_training_split: false,
      errors: { tr_rmse_c: null },
    };
  }
  return {
    batch_key: key,
    mode: "excel_only",
    message: "No panel telemetry for this batch. Showing Excel mass-log fields only.",
    excel: batch,
    t_offset_s: [],
    measured: { tr_c: [] },
    simulated: { tr_c: [] },
    process_state_measured: [],
    in_training_split: Boolean(batch.in_training_split),
    errors: { tr_rmse_c: null },
  };
}

export function demoTelemetry(machineId: number) {
  return {
    machine_id: machineId,
    samples: [],
    message: "No panel telemetry in Vercel demo mode.",
  };
}

export function trainingRanges() {
  const rows = (plantBatches as { batches: Array<{ feed_mass_kg: number | null }> }).batches;
  const feeds = rows.map((b) => b.feed_mass_kg).filter((v): v is number => typeof v === "number");
  const min = feeds.length ? Math.min(...feeds) : 9500;
  const max = feeds.length ? Math.max(...feeds) : 13650;
  return {
    feed_mass_kg: [min, max],
    target_peak_tr_c: [420, 480] as [number, number],
  };
}

export function demoSimulate(body: {
  feed_mass_kg: number;
  feedstock_type?: string;
  target_peak_tr_c: number;
  machine_id?: number;
  moisture_pct?: number;
}) {
  const feed = body.feed_mass_kg;
  const peak = body.target_peak_tr_c;
  const mid = body.machine_id ?? 1093;
  const ranges = trainingRanges();
  type Row = {
    machine_id: number;
    oil_yield_pct: number | null;
    steel_yield_pct: number | null;
    total_duration_min: number | null;
    feed_mass_kg: number | null;
  };
  const history = (plantBatches as { batches: Row[] }).batches.filter((b) => b.machine_id === mid);
  const avg = (key: keyof Row, fallback: number) => {
    const vals = history.map((b) => b[key]).filter((v): v is number => typeof v === "number");
    if (!vals.length) return fallback;
    return vals.reduce((a, b) => a + b, 0) / vals.length;
  };
  const baseOil = avg("oil_yield_pct", 35);
  const baseSteel = avg("steel_yield_pct", 12);
  const baseTime = avg("total_duration_min", 2000);
  const baseFeed = avg("feed_mass_kg", 10500);

  const blocking: string[] = [];
  if (feed < ranges.feed_mass_kg[0] || feed > ranges.feed_mass_kg[1]) {
    blocking.push(
      `Feed ${feed} kg is outside the logged training range ${ranges.feed_mass_kg[0]}–${ranges.feed_mass_kg[1]} kg.`,
    );
  }
  if (peak < ranges.target_peak_tr_c[0] || peak > ranges.target_peak_tr_c[1]) {
    blocking.push(
      `Peak Tr ${peak} °C is outside the provisional range ${ranges.target_peak_tr_c[0]}–${ranges.target_peak_tr_c[1]} °C.`,
    );
  }

  if (blocking.length) {
    return {
      input_echo: body,
      model_version: null,
      blocked: true,
      extrapolation_warnings: blocking,
      predicted_total_duration_min: null,
      phases: [],
      predicted_yields: null,
    };
  }

  const oil = Math.max(28, Math.min(48, baseOil + ((feed - baseFeed) / baseFeed) * 2));
  const steel = Math.max(8, Math.min(18, baseSteel));
  const duration = Math.round(baseTime + (feed - baseFeed) * 0.05);
  const label = mid === 1093 ? "R1" : mid === 1094 ? "R2" : "R3";
  return {
    input_echo: body,
    model_version: "excel-seed-v1",
    blocked: false,
    predicted_total_duration_min: duration,
    extrapolation_warnings: [
      `${label} duration/oil anchored on ${history.length} Excel log batches. Carbon is not predicted (plant estimate only).`,
    ],
    phases: [],
    predicted_yields: {
      oil_yield_pct: { p10: oil - 2, p50: oil, p90: oil + 2 },
      steel_yield_pct: { p10: steel - 1, p50: steel, p90: steel + 1 },
    },
  };
}

export function demoInsights() {
  const n = (plantBatches as { n_batches?: number }).n_batches ?? 0;
  return {
    insights: [
      {
        severity: "warning",
        title: "DEMO DATA",
        detail: "Floor telemetry is synthetic. Batches come from the anonymized Excel mass log — not live PLC.",
      },
      {
        severity: "info",
        title: `${n} Excel batches loaded`,
        detail: "Oil/steel/time from plant log. Carbon is a plant estimate (not a measurement). Water recovered is an output, not feed moisture.",
      },
    ],
    claude_configured: false,
    claude_needs_workspace: false,
    mcp_hint: "Use the HTPP Digital Shadow MCP server with Claude Desktop for plant Q&A — see docs/MCP-CLAUDE.md",
    generated_at: new Date().toISOString(),
  };
}

export function demoCoverage() {
  const all = (plantBatches as { batches: Array<Record<string, unknown>> }).batches;
  const per_machine = MACHINE_IDS.map((id) => {
    const mine = all.filter((b) => b.machine_id === id);
    const missing = mine.filter((b) => (b.quality_flags as string[] | undefined)?.includes("excel_durations_missing"));
    return {
      machine_id: id,
      history_floor: mine[0]?.log_date ?? null,
      last_sample_at: null,
      n_samples: 0,
      n_excel_batches: mine.length,
      median_interval_s: null,
      daily: [],
      gaps: [],
      note: `${mine.length} Excel batch rows (not telemetry samples). ${missing.length} missing duration rows.`,
    };
  });
  const usable = all.filter((b) => b.usable_for_training).length;
  const missingDur = all.filter((b) => (b.quality_flags as string[])?.includes("excel_durations_missing")).length;
  return {
    per_machine,
    batches: {
      total: all.length,
      complete: all.length - missingDur,
      usable_for_training: usable,
      with_excel_log: all.length,
      with_fault: null,
      missing_durations: missingDur,
    },
    excel: {
      rows_parsed: all.length,
      rows_unmatched: 0,
      unmatched_detail: [],
      closure_status: "not_measurable",
      closure_error_pct: {},
    },
    unmapped_process_values: [],
    ingest_failures: [],
    note: "Data page reflects Excel batch counts only until panel telemetry is ingested.",
  };
}
