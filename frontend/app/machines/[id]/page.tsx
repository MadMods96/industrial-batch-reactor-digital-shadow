"use client";

import { useEffect, useState } from "react";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Scatter, Tooltip, XAxis, YAxis } from "recharts";
import { ValueWithUnit } from "@/components/ui/ValueWithUnit";
import { apiGet } from "@/lib/api";
import { tempToCss } from "@/components/scene/tempRamp";

type Sample = { sampledAt: string; trC: number | null; tsC: number | null; prBar: number | null; processState: string };

export default function MachinePage({ params }: { params: { id: string } }) {
  const [rows, setRows] = useState<Sample[]>([]);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    apiGet<{ samples: Sample[] }>(`/api/machines/${params.id}/telemetry?downsample=240`)
      .then((data) => setRows(data.samples))
      .catch((err: Error) => setError(err.message));
  }, [params.id]);
  const chart = rows.map((row, i) => ({ i, tr: row.trC, ts: row.tsC, pr: row.prBar }));
  return (
    <main className="page">
      <div className="kicker">Machine {params.id}</div>
      <h1 style={{ fontWeight: 500 }}>Measured points, not a joined line</h1>
      {error && <div className="banner">{error}</div>}
      <div className="panel" style={{ height: 360, padding: 12 }}>
        <ResponsiveContainer>
          <LineChart data={chart}>
            <CartesianGrid stroke="rgba(255,255,255,0.06)" />
            <XAxis dataKey="i" stroke="#8ea0ab" />
            <YAxis stroke="#8ea0ab" unit=" °C" />
            <Tooltip />
            <Scatter dataKey="tr" fill={tempToCss(450)} />
            <Line dataKey="ts" stroke="var(--simulated)" dot={false} name="ts model-free connector" />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <p style={{ color: "var(--muted)" }}>
        Latest Tr <ValueWithUnit value={rows.at(-1)?.trC} unit="°C" />. Red is reserved for faults, so temperature uses the shared heat ramp.
      </p>
    </main>
  );
}
