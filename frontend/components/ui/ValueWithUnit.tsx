"use client";

export function ValueWithUnit({
  value,
  unit,
  digits = 1,
}: {
  value: number | null | undefined;
  unit: string;
  digits?: number;
}) {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return <span className="nodata">no data</span>;
  }
  return (
    <span className="mono">
      {value.toFixed(digits)}
      <span className="unit">{unit}</span>
    </span>
  );
}

export function PredictionInterval({
  p10,
  p50,
  p90,
  unit,
}: {
  p10: number | null | undefined;
  p50: number | null | undefined;
  p90: number | null | undefined;
  unit: string;
}) {
  if (p10 == null || p50 == null || p90 == null) return <span className="nodata">no interval</span>;
  const span = Math.max(p90 - p10, 0.001);
  const mid = ((p50 - p10) / span) * 100;
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 8, minWidth: 180 }}>
      <span style={{ position: "relative", flex: 1, height: 10, background: "var(--brand-soft)", borderRadius: 99 }}>
        <span style={{ position: "absolute", left: 0, right: 0, top: 4, height: 2, background: "var(--simulated)" }} />
        <span style={{ position: "absolute", left: `${mid}%`, top: 0, width: 3, height: 10, background: "var(--text)", borderRadius: 2 }} />
      </span>
      <span className="mono" style={{ fontSize: 12, color: "var(--text)" }}>
        {p50.toFixed(1)}
        <span className="unit">{unit}</span>
        <span style={{ color: "var(--muted)", marginLeft: 6 }}>({p10.toFixed(1)}–{p90.toFixed(1)})</span>
      </span>
    </span>
  );
}
