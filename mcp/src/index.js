#!/usr/bin/env node
/**
 * HTPP Digital Shadow MCP server — read-only tools over Excel-seeded batch history.
 * Intended for Claude Desktop (not the public Vercel Ask button).
 */

import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
} from "@modelcontextprotocol/sdk/types.js";

const __dirname = dirname(fileURLToPath(import.meta.url));
const DATA_PATH = join(__dirname, "..", "frontend", "lib", "demo", "plant_batches.json");

function load() {
  return JSON.parse(readFileSync(DATA_PATH, "utf8"));
}

function text(obj) {
  return { content: [{ type: "text", text: typeof obj === "string" ? obj : JSON.stringify(obj, null, 2) }] };
}

const server = new Server(
  { name: "htpp-digital-shadow", version: "0.1.0" },
  { capabilities: { tools: {} } },
);

server.setRequestHandler(ListToolsRequestSchema, async () => ({
  tools: [
    {
      name: "list_batches",
      description:
        "List anonymized Excel plant-log batches. Optional reactor filter R1|R2|R3. Returns batch_key, oil yield, duration, flags. Cite batch_key in answers.",
      inputSchema: {
        type: "object",
        properties: {
          reactor: { type: "string", description: "R1, R2, R3, or omit for all" },
          limit: { type: "number", description: "Max rows (default 40)" },
        },
      },
    },
    {
      name: "get_batch",
      description: "Fetch one batch by batch_key (e.g. R1-2026-08-01).",
      inputSchema: {
        type: "object",
        properties: { batch_key: { type: "string" } },
        required: ["batch_key"],
      },
    },
    {
      name: "summarize_yields",
      description:
        "Per-reactor average oil/steel yields and duration from Excel logs. Carbon is a plant estimate — say so. Never invent panel temperatures.",
      inputSchema: {
        type: "object",
        properties: {
          reactor: { type: "string", description: "Optional R1|R2|R3" },
        },
      },
    },
    {
      name: "data_notes",
      description: "Provenance notes: what is measured vs estimated vs missing in this seed.",
      inputSchema: { type: "object", properties: {} },
    },
  ],
}));

server.setRequestHandler(CallToolRequestSchema, async (request) => {
  const data = load();
  const batches = data.batches || [];
  const name = request.params.name;
  const args = request.params.arguments || {};

  if (name === "list_batches") {
    let rows = batches;
    if (args.reactor) {
      const r = String(args.reactor).toUpperCase();
      rows = rows.filter((b) => b.reactor === r);
    }
    const limit = Math.min(Number(args.limit) || 40, 120);
    return text({
      n: rows.length,
      showing: Math.min(limit, rows.length),
      batches: rows.slice(0, limit).map((b) => ({
        batch_key: b.batch_key,
        reactor: b.reactor,
        log_date: b.log_date,
        feed_mass_kg: b.feed_mass_kg,
        oil_yield_pct: b.oil_yield_pct,
        steel_yield_pct: b.steel_yield_pct,
        total_duration_min: b.total_duration_min,
        in_training_split: b.in_training_split,
        quality_flags: b.quality_flags,
      })),
    });
  }

  if (name === "get_batch") {
    const key = String(args.batch_key || "");
    const batch = batches.find((b) => b.batch_key === key);
    if (!batch) return text({ error: `Unknown batch_key ${key}` });
    return text(batch);
  }

  if (name === "summarize_yields") {
    let rows = batches;
    if (args.reactor) {
      rows = rows.filter((b) => b.reactor === String(args.reactor).toUpperCase());
    }
    const by = {};
    for (const b of rows) {
      const r = b.reactor || "?";
      by[r] ||= { n: 0, oil: [], steel: [], duration: [], carbon_estimate: [] };
      by[r].n += 1;
      if (b.oil_yield_pct != null) by[r].oil.push(b.oil_yield_pct);
      if (b.steel_yield_pct != null) by[r].steel.push(b.steel_yield_pct);
      if (b.total_duration_min != null) by[r].duration.push(b.total_duration_min);
      if (b.carbon_yield_pct != null) by[r].carbon_estimate.push(b.carbon_yield_pct);
    }
    const mean = (arr) => (arr.length ? arr.reduce((a, b) => a + b, 0) / arr.length : null);
    const summary = Object.fromEntries(
      Object.entries(by).map(([reactor, s]) => [
        reactor,
        {
          n_batches: s.n,
          mean_oil_yield_pct: mean(s.oil),
          mean_steel_yield_pct: mean(s.steel),
          mean_duration_min: mean(s.duration),
          mean_carbon_estimate_pct: mean(s.carbon_estimate),
          note: "carbon is plant estimate, not a lab assay",
        },
      ]),
    );
    return text({ summary, cite: "Excel plant mass log seed; not live PLC" });
  }

  if (name === "data_notes") {
    return text({
      source: data.source,
      note: data.note,
      n_batches: data.n_batches,
      rules: [
        "One-way digital shadow — never actuate the plant.",
        "Cite batch_key when stating yields.",
        "Carbon is estimated by the plant; do not present as measured.",
        "Net moisture / water_recovered_kg is an output, not feed moisture.",
        "Duration = sum of phase hour columns × 60 (not the sheet typo column).",
        "No live panel temperatures in this MCP seed.",
      ],
    });
  }

  return text({ error: `Unknown tool ${name}` });
});

const transport = new StdioServerTransport();
await server.connect(transport);
