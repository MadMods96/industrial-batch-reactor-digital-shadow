"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { apiGet, apiPost } from "@/lib/api";
import { MarkdownText } from "@/components/ui/MarkdownText";

type ChatTurn = { role: "user" | "assistant"; content: string };

export function AssistantDock() {
  const [open, setOpen] = useState(false);
  const [fullscreen, setFullscreen] = useState(false);
  const [claudeReady, setClaudeReady] = useState(true);
  const [needsWorkspace, setNeedsWorkspace] = useState(false);
  const [messages, setMessages] = useState<ChatTurn[]>([
    {
      role: "assistant",
      content: "Ask about yields, gaps, faults, or batch keys. I only read shadow data — I never change the reactor.",
    },
  ]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const scroller = useRef<HTMLDivElement>(null);

  useEffect(() => {
    apiGet<{ claudeConfigured: boolean; claudeNeedsWorkspace?: boolean }>("/api/assistant/insights")
      .then((data) => {
        setClaudeReady(Boolean(data.claudeConfigured));
        setNeedsWorkspace(Boolean(data.claudeNeedsWorkspace));
      })
      .catch(() => setClaudeReady(false));
  }, []);

  useEffect(() => {
    if (open && scroller.current) {
      scroller.current.scrollTop = scroller.current.scrollHeight;
    }
  }, [messages, open, busy, fullscreen]);

  useEffect(() => {
    if (!open) setFullscreen(false);
  }, [open]);

  useEffect(() => {
    if (!fullscreen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setFullscreen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [fullscreen]);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    const text = draft.trim();
    if (!text || busy) return;
    const next = [...messages, { role: "user" as const, content: text }];
    setMessages(next);
    setDraft("");
    setBusy(true);
    setError(null);
    try {
      const result = await apiPost<{ reply: string }>("/api/assistant/chat", {
        messages: next.map((m) => ({ role: m.role, content: m.content })),
      });
      setMessages([...next, { role: "assistant", content: result.reply }]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Chat failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={`assistant-dock${fullscreen ? " is-fullscreen" : ""}`}>
      {open && (
        <section
          className={`assistant-panel panel assistant-panel-chat${fullscreen ? " is-fullscreen" : ""}`}
          aria-label="Ask the shadow"
        >
          <header className="assistant-head">
            <div>
              <div className="kicker">Ask</div>
              <strong>Plant questions</strong>
            </div>
            <div className="assistant-head-actions">
              <button
                type="button"
                className="assistant-tool"
                onClick={() => setFullscreen((value) => !value)}
                aria-pressed={fullscreen}
              >
                {fullscreen ? "Exit full screen" : "Full screen"}
              </button>
              <button type="button" className="assistant-x" onClick={() => setOpen(false)} aria-label="Close">
                ×
              </button>
            </div>
          </header>

          {!claudeReady && (
            <p className="assistant-note" style={{ padding: "8px 12px 0" }}>
              {needsWorkspace ? (
                <>Assistant needs a workspace id in server env (not shown in the UI).</>
              ) : (
                <>Assistant API key is not configured on the server.</>
              )}
            </p>
          )}

          <div className="assistant-thread" ref={scroller}>
            {messages.map((turn, index) => (
              <div key={`${turn.role}-${index}`} className={`assistant-bubble ${turn.role}`}>
                {turn.role === "assistant" ? <MarkdownText text={turn.content} /> : turn.content}
              </div>
            ))}
            {busy && <div className="assistant-bubble assistant">Thinking…</div>}
          </div>

          {error && <div className="assistant-error">{error}</div>}

          <form className="assistant-form" onSubmit={onSubmit}>
            <input
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              placeholder="e.g. Why is R2 oil yield low?"
              disabled={busy}
            />
            <button type="submit" disabled={busy || !draft.trim()}>
              Ask
            </button>
          </form>
        </section>
      )}

      {!fullscreen && (
        <button
          type="button"
          className="assistant-fab"
          onClick={() => setOpen((value) => !value)}
          aria-expanded={open}
          aria-label="Ask a question"
        >
          <span>Ask</span>
        </button>
      )}
    </div>
  );
}
