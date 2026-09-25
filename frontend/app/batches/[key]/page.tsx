"use client";

import { useEffect, useState } from "react";
import { CartesianGrid, Line, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis } from "recharts";
import { apiGet } from "@/lib/api";
import { ValueWithUnit } from "@/components/ui/ValueWithUnit";

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
    apiGet<Replay>(`/api/batches/${params.key}/replay`).then(setData).catch((err: Error) => setError(err.message));
  }, [params.key]);
  const points = (data?.tOffsetS ?? []).map((t, i) => ({
    t: t / 60,
    measured: data?.measured.trC[i],
    simulated: data?.simulated.trC[i],
  }));
  const state = data?.processStateMeasured[index];
  return (
    <main className="page">
      <div className="kicker">Replay {params.key}</div>
      <h1 style={{ fontWeight: 500 }}>{state ?? "loading"}</h1>
      {data?.inTrainingSplit && <div className="banner">This batch is in the training split. A prediction here is not evidence.</div>}
      {error && <div className="banner">{error}</div>}
      <div className="panel" style={{ height: 340, padding: 12 }}>
        <ResponsiveContainer>
          <ScatterChart>
            <CartesianGrid stroke="rgba(255,255,255,0.06)" />
            <XAxis dataKey="t" name="min" stroke="#8ea0ab" />
            <YAxis dataKey="measured" stroke="#8ea0ab" unit=" °C" />
            <Tooltip />
            <Scatter data={points} dataKey="measured" fill="#d5dee6" />
            <Line data={points} dataKey="simulated" stroke="#3dbea0" dot={false} />
          </ScatterChart>
        </ResponsiveContainer>
      </div>
      <input type="range" min={0} max={Math.max(points.length - 1, 0)} value={index} onChange={(e) => setIndex(Number(e.target.value))} style={{ width: "100%" }} />
      <p>Trajectory RMSE <ValueWithUnit value={data?.errors.trRmseC} unit="°C" />. Measured values stay discrete dots.</p>
    </main>
  );
}
