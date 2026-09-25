"use client";

import { FormEvent, useState } from "react";
import { apiPost } from "@/lib/api";

type Interval = { p10: number; p50: number; p90: number };

type Result = {
  predictedTotalDurationMin: number;
  extrapolationWarnings: string[];
  phases?: Array<{ processState: string; durationMin: number }>;
  predictedYields: {
    oilYieldPct: Interval;
    carbonYieldPct: Interval;
    steelYieldPct: Interval;
  };
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
  const [moisture, setMoisture] = useState(6.5);
  const [peak, setPeak] = useState(455);
  const [rows, setRows] = useState<MachineResult[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const body = {
        feed_mass_kg: feed,
        moisture_pct: moisture,
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
            return { ...machine, result: null, error: humanError(err) } satisfies MachineResult;
          }
        }),
      );
      setRows(settled);
      if (settled.every((row) => !row.result)) {
        setError(settled[0]?.error || "Estimate failed for all reactors.");
      }
    } catch (err) {
      setRows(null);
      setError(humanError(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="page sim-page">
      <div className="kicker">What-if</div>
      <h1>See a batch estimate before you run it</h1>
      <p className="sim-lead">
        Enter charge, moisture, and target temperature once. The shadow estimates all three
        reactors side by side so you can compare time and yields. Advice only — nothing on the
        panel is changed.
      </p>

      <div className="sim-layout">
        <form className="panel sim-form" onSubmit={onSubmit}>
          <div className="sim-section-title">Charge details</div>
          <p className="sim-compare-note">Estimates run for <strong>R1, R2, and R3</strong> together.</p>

          <label className="sim-field">
            <span>Feed charge</span>
            <div className="sim-input">
              <input type="number" min={1000} max={20000} step={50} value={feed} onChange={(e) => setFeed(Number(e.target.value))} />
              <em>kg</em>
            </div>
            <small>Plant logs usually sit near 9,500–12,900 kg.</small>
          </label>

          <label className="sim-field">
            <span>Moisture</span>
            <div className="sim-input">
              <input type="number" min={0} max={20} step={0.1} value={moisture} onChange={(e) => setMoisture(Number(e.target.value))} />
              <em>%</em>
            </div>
            <small>Net moisture on feed. Typical logged band ~3–11%.</small>
          </label>

          <label className="sim-field">
            <span>Target peak Tr</span>
            <div className="sim-input">
              <input type="number" min={300} max={600} step={5} value={peak} onChange={(e) => setPeak(Number(e.target.value))} />
              <em>°C</em>
            </div>
            <small>Reactor temperature goal for heating / gas.</small>
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
              <p>Enter values on the left and click “Estimate all reactors”. R1, R2, and R3 will appear in one row.</p>
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

  const hours = (result.predictedTotalDurationMin / 60).toFixed(1);
  const caution = (result.extrapolationWarnings || []).some((w) =>
    /outside typical|outside the usual/i.test(w),
  );

  return (
    <article className="panel sim-reactor-card">
      <header className="sim-reactor-head">
        <div className="sim-reactor-short">{row.short}</div>
        <div className="kicker">{row.label}</div>
      </header>

      {caution && (
        <div className="sim-reactor-caution">Outside typical history — treat as a rough guide.</div>
      )}

      <div className="sim-reactor-time">
        <div className="kicker">Batch time</div>
        <div className="sim-reactor-time-value">
          {Math.round(result.predictedTotalDurationMin)}
          <span>min</span>
        </div>
        <p>About <strong>{hours} h</strong></p>
      </div>

      <div className="sim-reactor-yields">
        <div className="kicker">Yields</div>
        <YieldLine label="Oil" interval={result.predictedYields.oilYieldPct} />
        <YieldLine label="Carbon" interval={result.predictedYields.carbonYieldPct} />
        <YieldLine label="Steel" interval={result.predictedYields.steelYieldPct} />
      </div>

      {!!result.phases?.length && (
        <div className="sim-reactor-phases">
          <div className="kicker">Phases</div>
          {result.phases.map((phase) => (
            <div key={`${row.id}-${phase.processState}`} className="sim-phase">
              <span>{phaseLabel(phase.processState)}</span>
              <strong className="mono">{Math.round(phase.durationMin)} min</strong>
            </div>
          ))}
        </div>
      )}
    </article>
  );
}

function YieldLine({ label, interval }: { label: string; interval: Interval }) {
  return (
    <div className="sim-yield-line">
      <span>{label}</span>
      <strong className="mono">{interval.p50.toFixed(1)}%</strong>
      <small className="mono">{interval.p10.toFixed(1)}–{interval.p90.toFixed(1)}</small>
    </div>
  );
}

function phaseLabel(state: string) {
  const map: Record<string, string> = {
    heating: "Heating",
    gas: "Gas / process",
    cooling: "Cooling",
    n2_purging: "N₂ purge",
    carbon_discharge: "Carbon out",
    main_door_open: "Door open",
    idle: "Idle",
    solenoid_on: "Solenoid",
  };
  return map[state] || state.replaceAll("_", " ");
}

function humanError(err: unknown) {
  const text = err instanceof Error ? err.message : "Request failed";
  if (text.includes("Failed to fetch") || text.includes("NetworkError")) {
    return "Cannot reach the API. Start the backend first (port 8000).";
  }
  return text.replace(/[{}"\[\]]/g, " ").replace(/\s+/g, " ").trim();
}
