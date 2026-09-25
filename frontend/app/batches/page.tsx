"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { ValueWithUnit } from "@/components/ui/ValueWithUnit";
import { apiGet } from "@/lib/api";

type Batch = {
  batchKey: string;
  reactor?: string;
  machineId: number;
  batchNo: number | null;
  logDate?: string;
  totalDurationMin: number | null;
  peakTrC: number | null;
  hadFault: boolean | null;
  usableForTraining: boolean | null;
  inTrainingSplit?: boolean;
  oilYieldPct: number | null;
  qualityFlags: string[];
};

export default function BatchesPage() {
  const [rows, setRows] = useState<Batch[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [reactor, setReactor] = useState<string>("all");
  const [sort, setSort] = useState<"date" | "oil" | "duration">("date");

  useEffect(() => {
    apiGet<{ batches: Batch[] }>("/api/batches?limit=500")
      .then((data) => setRows(data.batches))
      .catch((err: Error) => setError(err.message));
  }, []);

  const filtered = useMemo(() => {
    let list = rows;
    if (reactor !== "all") list = list.filter((r) => (r.reactor || "").toUpperCase() === reactor);
    const copy = [...list];
    copy.sort((a, b) => {
      if (sort === "oil") return (b.oilYieldPct ?? -1) - (a.oilYieldPct ?? -1);
      if (sort === "duration") return (b.totalDurationMin ?? -1) - (a.totalDurationMin ?? -1);
      return (b.logDate || b.batchKey).localeCompare(a.logDate || a.batchKey);
    });
    return copy;
  }, [rows, reactor, sort]);

  return (
    <main className="page">
      <div className="kicker">Batch explorer</div>
      <h1 style={{ fontWeight: 500 }}>Every batch the shadow has seen</h1>
      <p style={{ color: "var(--muted)", maxWidth: "70ch" }}>
        Excel mass log: duration = sum of phase hours × 60. Carbon is a plant estimate.
        Water recovered is an output. Keys are <span className="mono">R1-YYYY-MM-DD</span> until panel join is confirmed.
      </p>
      {error && <div className="banner">{error}</div>}

      <div className="batch-filters">
        <label>
          Reactor{" "}
          <select value={reactor} onChange={(e) => setReactor(e.target.value)}>
            <option value="all">All</option>
            <option value="R1">R1</option>
            <option value="R2">R2</option>
            <option value="R3">R3</option>
          </select>
        </label>
        <label>
          Sort{" "}
          <select value={sort} onChange={(e) => setSort(e.target.value as typeof sort)}>
            <option value="date">Date</option>
            <option value="oil">Oil yield</option>
            <option value="duration">Duration</option>
          </select>
        </label>
      </div>

      <div className="panel table-wrap">
        <table>
          <thead>
            <tr>
              <th>Batch</th>
              <th>Reactor</th>
              <th>Duration</th>
              <th>Peak Tr</th>
              <th>Oil yield</th>
              <th>Split</th>
              <th>Flags</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((row) => (
              <tr key={row.batchKey}>
                <td>
                  <Link href={`/batches/${encodeURIComponent(row.batchKey)}`}>{row.batchKey}</Link>
                </td>
                <td>{row.reactor ?? "—"}</td>
                <td>
                  <ValueWithUnit value={row.totalDurationMin} unit="min" digits={0} />
                </td>
                <td>
                  <ValueWithUnit value={row.peakTrC} unit="°C" />
                </td>
                <td>
                  <ValueWithUnit value={row.oilYieldPct} unit="%" />
                </td>
                <td>{row.inTrainingSplit ? "train" : "holdout"}</td>
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
