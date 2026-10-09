"use client";

import { useEffect, useState } from "react";
import { CartesianGrid, Line, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis } from "recharts";
import { apiGet } from "@/lib/api";
import { ValueWithUnit } from "@/components/ui/ValueWithUnit";
import Link from "next/link";

type Replay = {
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
  const [index, setIndex] = useState(0);

  useEffect(() => {
    apiGet<Replay>(`/api/batches/${encodeURIComponent(params.key)}/replay`)
      .then(setData)
      .catch((err: Error) => setError(err.message));
  }, [params.key]);

  const points = (data?.tOffsetS ?? []).map((t, i) => ({
    t: t / 60,
    measured: data?.measured.trC[i] ?? null,
    simulated: data?.simulated.trC[i] ?? null,
  }));
  const state = data?.processStateMeasured?.[index];

  return (
    <main className="page">
      <div className="kicker">
        <Link href="/batches">Batches</Link> · Replay
      </div>
      <h1 style={{ fontWeight: 500 }}>{state ?? params.key}</h1>
      {data?.inTrainingSplit && (
        <div className="banner">This batch is in the training split. A prediction here is not evidence.</div>
      )}
      {error && <div className="banner">{error}</div>}
      {!error && points.length === 0 && (
        <div className="panel" style={{ padding: 16 }}>No telemetry replay for this batch yet.</div>
      )}
      {points.length > 0 && (
        <>
          <div className="panel" style={{ height: 340, padding: 12 }}>
            <ResponsiveContainer>
              <ScatterChart>
                <CartesianGrid stroke="rgba(16,32,41,0.08)" />
                <XAxis dataKey="t" name="min" stroke="#5a6d7a" />
                <YAxis dataKey="measured" stroke="#5a6d7a" unit=" °C" />
                <Tooltip />
                <Scatter data={points} dataKey="measured" fill="#102029" />
                <Line data={points} dataKey="simulated" stroke="#0b5f56" dot={false} />
              </ScatterChart>
            </ResponsiveContainer>
          </div>
          <input
            type="range"
            min={0}
            max={Math.max(points.length - 1, 0)}
            value={index}
            onChange={(e) => setIndex(Number(e.target.value))}
            style={{ width: "100%" }}
          />
          <p>
            Trajectory RMSE <ValueWithUnit value={data?.errors.trRmseC ?? null} unit="°C" />. Measured values stay
            discrete dots.
          </p>
        </>
      )}
    </main>
  );
}
