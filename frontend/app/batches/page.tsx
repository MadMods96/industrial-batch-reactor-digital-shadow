"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ValueWithUnit } from "@/components/ui/ValueWithUnit";
import { apiGet } from "@/lib/api";

type Batch = {
  batchKey: string;
  machineId: number;
  batchNo: number;
  totalDurationMin: number;
  peakTrC: number | null;
  hadFault: boolean;
  usableForTraining: boolean;
  oilYieldPct: number | null;
  qualityFlags: string[];
};

export default function BatchesPage() {
  const [rows, setRows] = useState<Batch[]>([]);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    apiGet<{ batches: Batch[] }>("/api/batches?limit=200")
      .then((data) => setRows(data.batches))
      .catch((err: Error) => setError(err.message));
  }, []);
  return (
    <main className="page">
      <div className="kicker">Batch explorer</div>
      <h1 style={{ fontWeight: 500 }}>Every batch the shadow has seen</h1>
      <p style={{ color: "var(--muted)", maxWidth: "62ch" }}>
        Seeded from the anonymized plant Excel mass log (feed / moisture / oil / carbon / steel / time).
        New live rows need a persistent store (DuckDB / DB) — Vercel demo does not append yet.
      </p>
      {error && <div className="banner">{error}. Run the API, then seed or backfill.</div>}
      {!rows.length && !error && <div className="panel" style={{ padding: 16 }}>No batches yet. Run <span className="mono">python -m htpp.cli seed</span> or backfill.</div>}
      <div className="panel table-wrap">
        <table>
          <thead>
            <tr>
              <th>Batch</th><th>Duration</th><th>Peak Tr</th><th>Oil yield</th><th>Training</th><th>Flags</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.batchKey}>
                <td><Link href={`/batches/${row.batchKey}`}>{row.batchKey}</Link></td>
                <td><ValueWithUnit value={row.totalDurationMin} unit="min" digits={0} /></td>
                <td><ValueWithUnit value={row.peakTrC} unit="°C" /></td>
                <td><ValueWithUnit value={row.oilYieldPct} unit="%" /></td>
                <td>{row.usableForTraining ? "yes" : "no"}</td>
                <td>{row.qualityFlags.join(", ") || "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </main>
  );
}
