"use client";

import { FormEvent, useEffect, useState } from "react";
import { apiGet, apiPost } from "@/lib/api";

type Interval = { p10: number; p50: number; p90: number };

type Result = {
  predictedTotalDurationMin: number | null;
  extrapolationWarnings: string[];
  blocked?: boolean;
  phases?: Array<{ processState: string; durationMin: number }>;
  predictedYields: {
    oilYieldPct: Interval;
    steelYieldPct: Interval;
    carbonYieldPct?: Interval;
  } | null;
};

type MachineResult = {
  id: number;
  label: string;
  short: string;
  result: Result | null;
  error: string | null;
};

const MACHINES = [
  { id: 1093, short: "R1", label: "Unit 1" },
  { id: 1094, short: "R2", label: "Unit 2" },
  { id: 1146, short: "R3", label: "Unit 3" },
];

export default function SimulatePage() {
  const [feed, setFeed] = useState(10500);
  const [peak, setPeak] = useState(455);
  const [feedMin, setFeedMin] = useState(9500);
  const [feedMax, setFeedMax] = useState(13650);
  const [rows, setRows] = useState<MachineResult[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiGet<{ feedMassKg: [number, number] }>("/api/training-ranges")
      .then((r) => {
        setFeedMin(Math.floor(r.feedMassKg[0]));
        setFeedMax(Math.ceil(r.feedMassKg[1]));
      })
      .catch(() => undefined);
  }, []);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const body = {
        feed_mass_kg: feed,
        feedstock_type: "tyre",
        target_peak_tr_c: peak,
        heating_power_scale: 1,
        amb_temp_c: 28.5,
        step_s: 60,
      };
      const settled = await Promise.all(
        MACHINES.map(async (machine) => {
          try {
            const result = await apiPost<Result>("/api/simulate", {
              ...body,
              machine_id: machine.id,
            });
            return { ...machine, result, error: null } satisfies MachineResult;
          } catch (err) {
            return {
              ...machine,
              result: null,
              error: err instanceof Error ? err.message : "Estimate failed",
            } satisfies MachineResult;
          }
        }),
      );
      setRows(settled);
      if (settled.every((row) => !row.result || row.result.blocked)) {
        setError(settled[0]?.result?.extrapolationWarnings?.[0] || settled[0]?.error || "Estimate blocked.");
      }
    } catch (err) {
      setRows(null);
      setError(err instanceof Error ? err.message : "Estimate failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="page sim-page">
      <div className="kicker">What-if</div>
      <h1>See a batch estimate before you run it</h1>
      <p className="sim-lead">
        Charge and target peak only. Water recovered is an Excel <em>output</em>, not a feed input.
        Carbon is a plant estimate — not predicted here. Advice only.
      </p>

      <div className="sim-layout">
        <form className="panel sim-form" onSubmit={onSubmit}>
          <div className="sim-section-title">Charge details</div>
          <p className="sim-compare-note">
            Estimates for <strong>R1, R2, and R3</strong>. Training feed range {feedMin}–{feedMax} kg.
          </p>

          <label className="sim-field">
            <span>Feed charge</span>
            <div className="sim-input">
              <input
                type="number"
                min={feedMin}
                max={feedMax}
                step={50}
                value={feed}
                onChange={(e) => setFeed(Number(e.target.value))}
              />
              <em>kg</em>
            </div>
            <small>Logged plant range {feedMin}–{feedMax} kg.</small>
          </label>

          <label className="sim-field">
            <span>Target peak Tr</span>
            <div className="sim-input">
              <input type="number" min={420} max={480} step={5} value={peak} onChange={(e) => setPeak(Number(e.target.value))} />
              <em>°C</em>
            </div>
            <small>Provisional peak band until panel join exists.</small>
          </label>

          <button type="submit" className="sim-submit" disabled={busy}>
            {busy ? "Estimating R1–R3…" : "Estimate all reactors"}
          </button>
        </form>

        <section className="sim-results">
          {error && <div className="banner">{error}</div>}
          {!rows && !error && (
            <div className="panel sim-empty">
              <strong>No estimate yet</strong>
              <p>Enter charge and peak, then estimate all three reactors.</p>
            </div>
          )}
          {rows && (
            <div className="sim-compare-row">
              {rows.map((row) => (
                <ReactorCard key={row.id} row={row} />
              ))}
            </div>
          )}
        </section>
      </div>
    </main>
  );
}

function ReactorCard({ row }: { row: MachineResult }) {
  const result = row.result;
  if (!result) {
    return (
      <article className="panel sim-reactor-card">
        <header className="sim-reactor-head">
          <div className="sim-reactor-short">{row.short}</div>
          <div className="kicker">{row.label}</div>
        </header>
        <p className="sim-reactor-error">{row.error || "No result"}</p>
      </article>
    );
  }

  if (result.blocked || result.predictedTotalDurationMin == null || !result.predictedYields) {
    return (
      <article className="panel sim-reactor-card">
        <header className="sim-reactor-head">
          <div className="sim-reactor-short">{row.short}</div>
          <div className="kicker">{row.label}</div>
        </header>
        <div className="banner">
          {(result.extrapolationWarnings || []).join(" ") || "Outside training range — estimate withheld."}
        </div>
      </article>
    );
  }

  const hours = (result.predictedTotalDurationMin / 60).toFixed(1);
  return (
    <article className="panel sim-reactor-card">
      <header className="sim-reactor-head">
        <div className="sim-reactor-short">{row.short}</div>
        <div className="kicker">{row.label}</div>
      </header>
      <div className="sim-reactor-time">
        <div className="kicker">Batch time</div>
        <strong>{result.predictedTotalDurationMin} min</strong>
        <span className="mono">≈ {hours} h</span>
      </div>
      <div className="sim-yields">
        <div className="kicker">Yields</div>
        <div>Oil {result.predictedYields.oilYieldPct.p50.toFixed(1)}%</div>
        <div className="mono">
          {result.predictedYields.oilYieldPct.p10.toFixed(1)}–{result.predictedYields.oilYieldPct.p90.toFixed(1)}
        </div>
        <div>Steel {result.predictedYields.steelYieldPct.p50.toFixed(1)}%</div>
        <div className="mono">
          {result.predictedYields.steelYieldPct.p10.toFixed(1)}–{result.predictedYields.steelYieldPct.p90.toFixed(1)}
        </div>
        <p className="mono" style={{ marginTop: 8, color: "var(--muted)" }}>
          Carbon not predicted (plant estimate in Excel).
        </p>
      </div>
    </article>
  );
}
