"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { ValueWithUnit } from "@/components/ui/ValueWithUnit";
import { apiGet } from "@/lib/api";

type Batch = {
  batchKey: string;
  machineId: number;
  batchNo: number | null;
  totalDurationMin: number | null;
  peakTrC: number | null;
  hadFault: boolean | null;
  usableForTraining: boolean | null;
  oilYieldPct: number | null;
  qualityFlags: string[];
};

const LABELS: Record<number, string> = {
  1093: "R1",
  1094: "R2",
  1146: "R3",
};

export default function BatchesPage() {
  const [rows, setRows] = useState<Batch[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [machine, setMachine] = useState<string>("all");

  useEffect(() => {
    apiGet<{ batches: Batch[] }>("/api/batches?limit=200")
      .then((data) => setRows(data.batches))
      .catch((err: Error) => setError(err.message));
  }, []);

  const filtered = useMemo(() => {
    if (machine === "all") return rows;
    return rows.filter((r) => String(r.machineId) === machine);
  }, [rows, machine]);

  return (
    <main className="page">
      <div className="kicker">Batch explorer</div>
      <h1 style={{ fontWeight: 500 }}>Every batch the shadow has seen</h1>
      <p style={{ color: "var(--muted)", maxWidth: "62ch" }}>
        Assembled from live panel telemetry and optional Excel mass log. Read-only digital shadow.
      </p>
      {error && <div className="banner">{error}. Is the API running?</div>}

      <div className="batch-filters">
        <label>
          Reactor{" "}
          <select value={machine} onChange={(e) => setMachine(e.target.value)}>
            <option value="all">All</option>
            <option value="1093">R1</option>
            <option value="1094">R2</option>
            <option value="1146">R3</option>
          </select>
        </label>
      </div>

      {!filtered.length && !error && (
        <div className="panel" style={{ padding: 16 }}>
          No batches yet. Run ingest / excel assemble on the API host.
        </div>
      )}

      <div className="panel table-wrap">
        <table>
          <thead>
            <tr>
              <th>Batch</th>
              <th>Reactor</th>
              <th>Duration</th>
              <th>Peak Tr</th>
              <th>Oil yield</th>
              <th>Training</th>
              <th>Flags</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((row) => (
              <tr key={row.batchKey}>
                <td>
                  <Link href={`/batches/${encodeURIComponent(row.batchKey)}`}>{row.batchKey}</Link>
                </td>
                <td>{LABELS[row.machineId] ?? row.machineId}</td>
                <td>
                  <ValueWithUnit value={row.totalDurationMin} unit="min" digits={0} />
                </td>
                <td>
                  <ValueWithUnit value={row.peakTrC} unit="°C" />
                </td>
                <td>
                  <ValueWithUnit value={row.oilYieldPct} unit="%" />
                </td>
                <td>{row.usableForTraining ? "yes" : "no"}</td>
                <td className="mono" style={{ whiteSpace: "normal", maxWidth: 220 }}>
                  {row.qualityFlags?.length ? row.qualityFlags.join(", ") : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </main>
  );
}
