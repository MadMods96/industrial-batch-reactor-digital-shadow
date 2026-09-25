"use client";

import { useState } from "react";

/** In-app Ask no longer calls Anthropic. Use Claude Desktop + MCP instead. */
export function AssistantDock() {
  const [open, setOpen] = useState(false);

  return (
    <div className="assistant-dock">
      {open && (
        <section className="assistant-panel panel assistant-panel-chat" aria-label="Ask via MCP">
          <header className="assistant-head">
            <div>
              <div className="kicker">Ask</div>
              <strong>Use Claude + MCP</strong>
            </div>
            <button type="button" className="assistant-x" onClick={() => setOpen(false)} aria-label="Close">
              ×
            </button>
          </header>
          <div className="assistant-thread">
            <div className="assistant-bubble assistant">
              The public site no longer calls the Anthropic API (no credit burn, no leaked billing errors).
            </div>
            <div className="assistant-bubble assistant">
              For plant Q&amp;A, connect the <strong>HTPP Digital Shadow MCP server</strong> to Claude Desktop.
              It can list batches, summarize yields, and read Excel-seeded history with citations.
            </div>
            <div className="assistant-bubble assistant">
              Setup: repo file <span className="mono">docs/MCP-CLAUDE.md</span>
              {" "}— then ask Claude things like “compare R1 vs R2 oil yield last month”.
            </div>
          </div>
        </section>
      )}
      <button type="button" className="assistant-fab" onClick={() => setOpen((v) => !v)} aria-expanded={open}>
        Ask
      </button>
    </div>
  );
}
