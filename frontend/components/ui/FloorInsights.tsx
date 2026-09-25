"use client";

import { useEffect, useState } from "react";
import { apiGet } from "@/lib/api";
import { MarkdownText } from "@/components/ui/MarkdownText";

export type Insight = {
  severity: "ok" | "warning" | "critical" | string;
  title: string;
  detail: string;
};

const PREVIEW = 3;

export function FloorInsights() {
  const [insights, setInsights] = useState<Insight[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [openAll, setOpenAll] = useState(false);

  useEffect(() => {
    let alive = true;
    const load = () => {
      apiGet<{ insights: Insight[]; claudeSummary?: string }>("/api/assistant/insights")
        .then((data) => {
          if (!alive) return;
          const rows = [...(data.insights || [])];
          if (data.claudeSummary) {
            rows.unshift({
              severity: "ok",
              title: "Plant brief",
              detail: data.claudeSummary,
            });
          }
          setInsights(rows);
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
            <div className="kicker">Live insights</div>
            <strong>Alerts & plant notes</strong>
          </div>
          <span className="mono floor-insights-count">{insights.length || 0}</span>
        </div>

        {error && <p className="assistant-note">{error}</p>}
        {!error && !insights.length && (
          <p className="assistant-note">No insights yet. Start the API and they will show up here.</p>
        )}

        <div className="insights-half-list">
          {preview.map((item) => (
            <article key={`${item.title}-${item.detail.slice(0, 40)}`} className="floor-insight">
              <span className={`dot ${item.severity === "ok" ? "ok" : item.severity}`} />
              <div>
                <strong>{item.title}</strong>
                <MarkdownText text={item.detail} />
              </div>
            </article>
          ))}
        </div>

        {insights.length > 0 && (
          <button type="button" className="insights-view-all" onClick={() => setOpenAll(true)}>
            View all ({insights.length})
          </button>
        )}
      </section>

      {openAll && (
        <div className="insights-modal-backdrop" role="presentation" onClick={() => setOpenAll(false)}>
          <div
            className="insights-modal panel"
            role="dialog"
            aria-modal="true"
            aria-label="All plant insights"
            onClick={(e) => e.stopPropagation()}
          >
            <header className="insights-modal-head">
              <div>
                <div className="kicker">Live insights</div>
                <strong>All alerts & plant notes</strong>
              </div>
              <div className="insights-modal-actions">
                <span className="mono floor-insights-count">{insights.length}</span>
                <button type="button" className="assistant-x" onClick={() => setOpenAll(false)} aria-label="Close">
                  ×
                </button>
              </div>
            </header>
            {error && <p className="assistant-note">{error}</p>}
            <div className="insights-modal-grid">
              {insights.map((item) => (
                <article key={`${item.title}-${item.detail.slice(0, 48)}`} className="floor-insight insights-modal-card">
                  <span className={`dot ${item.severity === "ok" ? "ok" : item.severity}`} />
                  <div>
                    <strong>{item.title}</strong>
                    <MarkdownText text={item.detail} />
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
