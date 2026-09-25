"use client";

import { useEffect, useState } from "react";
import { apiGet } from "@/lib/api";

type Coverage = {
  note?: string;
  perMachine: Array<{
    machineId: number;
    nSamples: number;
    nExcelBatches?: number;
    note?: string;
  }>;
  batches: {
    total: number;
    complete: number;
    usableForTraining: number;
    withExcelLog: number;
    withFault: number | null;
    missingDurations?: number;
  };
  excel: { rowsParsed: number; closureStatus?: string };
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
      <p style={{ color: "var(--muted)", maxWidth: "70ch" }}>
        Until panel telemetry is ingested, this page reports <strong>Excel batch counts</strong>, not 4-minute
        sample coverage. Closure is <span className="mono">not_measurable</span> without reliable gas.
      </p>
      {error && <div className="banner">{error}</div>}
      {data?.note && <div className="banner">{data.note}</div>}

      <div className="coverage-list">
        {(data?.perMachine ?? []).map((machine) => (
          <section key={machine.machineId} className="panel coverage-card">
            <div className="coverage-head">
              <strong>{LABELS[machine.machineId] ?? `Machine ${machine.machineId}`}</strong>
              <span className="mono">
                {machine.nExcelBatches ?? 0} Excel batches · {machine.nSamples} telemetry samples
              </span>
            </div>
            <p style={{ margin: 0, color: "var(--muted)" }}>{machine.note}</p>
          </section>
        ))}
      </div>

      {data && (
        <div className="panel" style={{ padding: 16, marginTop: 16 }}>
          <div className="kicker">Excel summary</div>
          <p className="mono" style={{ margin: "8px 0 0" }}>
            total {data.batches.total} · complete {data.batches.complete} · usable train{" "}
            {data.batches.usableForTraining} · missing durations {data.batches.missingDurations ?? "—"} ·
            closure {data.excel.closureStatus ?? "unknown"}
          </p>
        </div>
      )}
    </main>
  );
}
