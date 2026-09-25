"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ValueWithUnit } from "@/components/ui/ValueWithUnit";
import { apiGet } from "@/lib/api";

type Replay = {
  batchKey: string;
  mode?: string;
  message?: string;
  excel?: {
    feedMassKg?: number | null;
    oilYieldPct?: number | null;
    carbonYieldPct?: number | null;
    steelYieldPct?: number | null;
    totalDurationMin?: number | null;
    waterRecoveredKg?: number | null;
    qualityFlags?: string[];
    logDate?: string;
    reactor?: string;
  } | null;
  tOffsetS: number[];
  measured: { trC: Array<number | null> };
  simulated: { trC: number[] };
  processStateMeasured: string[];
  inTrainingSplit: boolean;
  errors: { trRmseC: number | null };
};

export default function ReplayPage({ params }: { params: { key: string } }) {
  const [data, setData] = useState<Replay | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiGet<Replay>(`/api/batches/${encodeURIComponent(params.key)}/replay`)
      .then(setData)
      .catch((err: Error) => setError(err.message));
  }, [params.key]);

  const excel = data?.excel;

  return (
    <main className="page">
      <div className="kicker">
        <Link href="/batches">Batches</Link> · Replay
      </div>
      <h1 style={{ fontWeight: 500 }}>{params.key}</h1>
      {error && <div className="banner">{error}</div>}
      {data?.inTrainingSplit && (
        <div className="banner">This batch is in the training split. Do not treat it as held-out evidence.</div>
      )}

      {data?.mode === "excel_only" && (
        <>
          <div className="banner">{data.message}</div>
          <div className="panel" style={{ padding: 16, display: "grid", gap: 8 }}>
            <div className="kicker">Excel mass log</div>
            <div>Reactor {excel?.reactor ?? "—"} · {excel?.logDate ?? "—"}</div>
            <div>
              Feed <ValueWithUnit value={excel?.feedMassKg ?? null} unit="kg" /> · Duration{" "}
              <ValueWithUnit value={excel?.totalDurationMin ?? null} unit="min" digits={0} />
            </div>
            <div>
              Oil <ValueWithUnit value={excel?.oilYieldPct ?? null} unit="%" /> · Steel{" "}
              <ValueWithUnit value={excel?.steelYieldPct ?? null} unit="%" />
            </div>
            <div>
              Carbon <ValueWithUnit value={excel?.carbonYieldPct ?? null} unit="%" />{" "}
              <span className="mono">(plant estimate)</span>
            </div>
            <div>
              Water recovered <ValueWithUnit value={excel?.waterRecoveredKg ?? null} unit="kg" />{" "}
              <span className="mono">(output, not feed moisture)</span>
            </div>
            <div className="mono">Flags: {excel?.qualityFlags?.join(", ") || "—"}</div>
          </div>
        </>
      )}

      {data && data.mode !== "excel_only" && (data.tOffsetS?.length ?? 0) === 0 && !error && (
        <div className="panel" style={{ padding: 16 }}>
          No panel telemetry for this batch.
        </div>
      )}
    </main>
  );
}
