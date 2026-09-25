"use client";

import { useEffect, useState } from "react";
import { apiGet } from "@/lib/api";

type Day = { date: string; nSamples: number };
type MachineCov = {
  machineId: number;
  nSamples: number;
  medianIntervalS: number | null;
  daily: Day[];
  gaps: Array<{ durationS: number }>;
};

type Coverage = {
  perMachine: MachineCov[];
  batches: {
    total: number;
    complete: number;
    usableForTraining: number;
    withExcelLog: number;
    withFault: number;
  };
  ingestFailures: unknown[];
};

const LABELS: Record<number, string> = {
  1093: "R1 Unit 1",
  1094: "R2 Unit 2",
  1146: "R3 Unit 3",
};

export default function DataPage() {
  const [data, setData] = useState<Coverage | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiGet<Coverage>("/api/data/coverage")
      .then(setData)
      .catch((err: Error) => setError(err.message));
  }, []);

  return (
    <main className="page">
      <div className="kicker">Data quality</div>
      <h1 style={{ fontWeight: 500 }}>Coverage, gaps, and what the panel did not say</h1>
      {error && <div className="banner">{error}</div>}

      <div className="coverage-list">
        {(data?.perMachine ?? []).map((machine) => {
          const longGaps = machine.gaps.filter((g) => g.durationS >= 1800).length;
          return (
            <section key={machine.machineId} className="panel coverage-card">
              <div className="coverage-head">
                <strong>{LABELS[machine.machineId] ?? `Machine ${machine.machineId}`}</strong>
                <span className="mono">
                  {machine.nSamples.toLocaleString()} samples · {longGaps} gaps over 30 min
                  {machine.medianIntervalS != null ? ` · ~${Math.round(machine.medianIntervalS / 60)} min median` : ""}
                </span>
              </div>
              <div className="coverage-heat" aria-label={`Coverage for ${machine.machineId}`}>
                {machine.daily.map((day) => (
                  <span
                    key={day.date}
                    title={`${day.date}: ${day.nSamples} samples`}
                    className={day.nSamples > 0 ? "heat-on" : "heat-off"}
                  />
                ))}
              </div>
            </section>
          );
        })}
      </div>

      {data && data.ingestFailures.length > 0 && (
        <div className="banner">Ingest failures recorded: {data.ingestFailures.length}.</div>
      )}

      {data && (
        <div className="panel" style={{ padding: 16, marginTop: 16 }}>
          <div className="kicker">Batches</div>
          <p className="mono" style={{ margin: "8px 0 0" }}>
            total {data.batches.total} · complete {data.batches.complete} · usable{" "}
            {data.batches.usableForTraining} · with excel {data.batches.withExcelLog} · with fault{" "}
            {data.batches.withFault}
          </p>
        </div>
      )}
    </main>
  );
}
