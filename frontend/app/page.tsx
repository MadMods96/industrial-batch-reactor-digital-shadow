"use client";

import dynamic from "next/dynamic";
import { useEffect, useState, type ReactNode } from "react";
import { ValueWithUnit } from "@/components/ui/ValueWithUnit";
import { FloorInsights } from "@/components/ui/FloorInsights";
import { connectLive } from "@/lib/ws";
import { sampleMachine, useLive, type MachineLive } from "@/lib/store";

const PlantScene = dynamic(() => import("@/components/scene/PlantScene").then((m) => m.PlantScene), { ssr: false });

const UNITS = [
  { id: 1093, short: "R1", name: "Unit 1" },
  { id: 1094, short: "R2", name: "Unit 2" },
  { id: 1146, short: "R3", name: "Unit 3" },
];

export default function OverviewPage() {
  const [webgl, setWebgl] = useState(true);
  const [hud, setHud] = useState<Record<number, ReturnType<typeof sampleMachine> & { machine: MachineLive }>>({});
  const status = useLive((s) => s.status);
  const version = useLive((s) => s.modelVersion);
  const alarms = useLive((s) => s.alarms);
  const camera = useLive((s) => s.camera);
  const post = useLive((s) => s.post);

  useEffect(() => {
    connectLive();
    const canvas = document.createElement("canvas");
    setWebgl(Boolean(canvas.getContext("webgl")));
    const id = window.setInterval(() => {
      const machines = useLive.getState().machines;
      const now = performance.now();
      const next: typeof hud = {};
      for (const machine of Object.values(machines)) {
        next[machine.machineId] = { ...sampleMachine(machine, now), machine };
      }
      setHud(next);
    }, 100);
    return () => window.clearInterval(id);
  }, []);

  return (
    <main className="floor-page">
      {webgl ? <PlantScene /> : <div className="page">WebGL is unavailable. Other pages still work.</div>}

      <aside className="floor-rail" aria-label="Plant status">
        <div className="floor-brand-block">
          <div className="kicker">Plant floor</div>
          <div className="floor-brand-mark">HTPP</div>
          <div className="mono floor-status-line">
            <span className={`dot ${status === "live" ? "ok" : "stale"}`} />
            {status} · {version ?? "no model"} · IST
          </div>
          <div className="stack-legend" aria-label="Tower light meaning">
            <span><i className="stack-dot green" /> Running</span>
            <span><i className="stack-dot amber" /> Processing stop</span>
            <span><i className="stack-dot blue" /> Idle</span>
            <span><i className="stack-dot red" /> Fault / offline</span>
          </div>
        </div>

        <section
          className="machine-stage"
          data-focus={camera.startsWith("reactor-") ? "single" : "all"}
          aria-label="Machine status"
        >
          {UNITS.filter(({ id }) => camera === "overview" || camera === "cutaway" || camera === `reactor-${id}`).map(
            ({ id, short, name }) => {
              const row = hud[id];
              const machine = row?.machine;
              const fault = machine?.faultState && machine.faultState !== "none";
              const focused = camera === `reactor-${id}`;
              return (
                <button
                  key={id}
                  className="machine-card"
                  onClick={() => useLive.getState().setCamera(focused ? "overview" : `reactor-${id}`)}
                  data-active={focused || camera === "overview" ? "true" : "false"}
                  style={{ borderColor: fault ? "var(--critical)" : undefined }}
                >
                  <div className="machine-card-top">
                    <div>
                      <div className="machine-card-short">{short}</div>
                      <div className="kicker">{name}</div>
                    </div>
                    <span className={`dot ${row?.stale ? "stale" : fault ? "critical" : "ok"}`} />
                  </div>
                  <div className="machine-card-state">{machine?.processRaw ?? "Waiting for data"}</div>
                  <div className="machine-card-grid">
                    <Metric label="Tr" value={<ValueWithUnit value={row?.tr} unit="°C" />} />
                    <Metric label="Ts" value={<ValueWithUnit value={row?.ts} unit="°C" />} />
                    <Metric label="Pr" value={<ValueWithUnit value={row?.pr} unit="bar" digits={2} />} />
                    <Metric label="Ps" value={<ValueWithUnit value={row?.ps} unit="bar" digits={2} />} />
                  </div>
                  <div className="machine-card-foot">
                    Batch {machine?.batchNo ?? "—"}
                    <span>·</span>
                    <ValueWithUnit value={machine?.batchElapsedMin} unit="min" digits={0} />
                    {row?.stale ? <span className="stale-tag">stale</span> : null}
                  </div>
                </button>
              );
            },
          )}
        </section>
      </aside>

      <div className="floor-view-tools">
        {[
          ["overview", "All"],
          ["reactor-1093", "R1"],
          ["reactor-1094", "R2"],
          ["reactor-1146", "R3"],
          ["cutaway", "Cutaway"],
        ].map(([mode, label]) => (
          <button key={mode} onClick={() => useLive.getState().setCamera(mode)} className={`chip ${camera === mode ? "on" : ""}`}>
            {label}
          </button>
        ))}
        <button onClick={() => useLive.getState().setPost(!post)} className={`chip ${post ? "on" : ""}`}>Bloom</button>
      </div>

      <div className="floor-alarms">
        {alarms.map((alarm) => (
          <button key={alarm.id} className="panel alarm-card" onClick={() => useLive.getState().dismiss(alarm.id)}>
            <div className="kicker">{alarm.severity}</div>
            {alarm.message}
          </button>
        ))}
      </div>

      <FloorInsights />
    </main>
  );
}

function Metric({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="metric">
      <span>{label}</span>
      {value}
    </div>
  );
}
