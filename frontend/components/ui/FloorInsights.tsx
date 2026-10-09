"use client";

import { useEffect, useState } from "react";
import { apiGet } from "@/lib/api";

export type Insight = {
  severity: "ok" | "warning" | "critical" | string;
  title: string;
  detail: string;
};

const PREVIEW = 3;

/** Rule-based plant notes from the API (no LLM). */
export function FloorInsights() {
  const [insights, setInsights] = useState<Insight[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [openAll, setOpenAll] = useState(false);

  useEffect(() => {
    let alive = true;
    const load = () => {
      apiGet<{ insights: Insight[] }>("/api/insights")
        .then((data) => {
          if (!alive) return;
          setInsights(data.insights || []);
          setError(null);
        })
        .catch((err: Error) => {
          if (alive) setError(err.message);
        });
    };
    load();
    const id = window.setInterval(load, 60_000);
    return () => {
      alive = false;
      window.clearInterval(id);
    };
  }, []);

  useEffect(() => {
    if (!openAll) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpenAll(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [openAll]);

  const preview = insights.slice(0, PREVIEW);

  return (
    <>
      <section className="insights-half panel" aria-label="Plant insights">
        <div className="insights-half-head">
          <div>
            <div className="kicker">Insights</div>
            <strong>Alerts & plant notes</strong>
          </div>
          <span className="mono floor-insights-count">{insights.length || 0}</span>
        </div>

        {error && <p className="assistant-note">{error}</p>}
        {!error && !insights.length && (
          <p className="assistant-note">No insights yet. Waiting for live telemetry.</p>
        )}

        <div className="insights-half-list">
          {preview.map((item) => (
            <article key={`${item.title}-${item.detail.slice(0, 40)}`} className="floor-insight">
              <span className={`dot ${item.severity === "ok" ? "ok" : item.severity}`} />
              <div>
                <strong>{item.title}</strong>
                <p>{item.detail}</p>
              </div>
            </article>
          ))}
        </div>

        {insights.length > PREVIEW && (
          <button type="button" className="insights-view-all" onClick={() => setOpenAll(true)}>
            View all ({insights.length})
          </button>
        )}
      </section>

      {openAll && (
        <div className="insights-modal-backdrop" onClick={() => setOpenAll(false)}>
          <div className="insights-modal panel" onClick={(e) => e.stopPropagation()}>
            <div className="insights-modal-head">
              <strong>All insights</strong>
              <button type="button" className="assistant-x" onClick={() => setOpenAll(false)} aria-label="Close">
                ×
              </button>
            </div>
            <div className="insights-modal-grid">
              {insights.map((item) => (
                <article key={`${item.title}-${item.detail.slice(0, 40)}`} className="insights-modal-card floor-insight">
                  <span className={`dot ${item.severity === "ok" ? "ok" : item.severity}`} />
                  <div>
                    <strong>{item.title}</strong>
                    <p>{item.detail}</p>
                  </div>
                </article>
              ))}
            </div>
          </div>
        </div>
      )}
    </>
  );
}
