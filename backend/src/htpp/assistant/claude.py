"""Claude client for plant Q&A. Key stays server-side in HTPP_ANTHROPIC_API_KEY."""

from __future__ import annotations

import os
from typing import Any

from htpp.assistant.context import briefing_text, plant_briefing, rule_insights
from htpp.config import settings
from htpp.plant import machine_label, plant_label

SYSTEM = f"""You are the HTPP Digital Shadow assistant for industrial batch reactors
({plant_label()}: machines mapped as 1093={machine_label(1093)}, 1094={machine_label(1094)}, 1146={machine_label(1146)}).

Rules:
- You only advise. You cannot actuate valves, change setpoints, or write to the panel.
- Use ONLY the plant briefing JSON and the user's question. If a number is missing, say so.
- Write for plant operators in plain English.
- Short headings and bullets are OK (Markdown). Do not dump JSON, ISO timestamps, or internal flag names like ingestion_gap.
- Say dates like "17 Sep 2026" and durations like "about 5 days". Use R1/R2/R3 names.
- Never invent or reveal customer, site, operator, email, password, or API credentials.
- Keep answers short: 2–6 sentences or a tight bullet list.
- Suggest operational checks, not speculative chemistry.
"""


class ClaudeConfigError(RuntimeError):
    pass


def api_key() -> str:
    return (settings.anthropic_api_key or os.environ.get("ANTHROPIC_API_KEY") or "").strip()


def workspace_id() -> str:
    return (settings.anthropic_workspace_id or os.environ.get("ANTHROPIC_WORKSPACE_ID") or "").strip()


def _client():
    key = api_key()
    if not key:
        raise ClaudeConfigError(
            "Set HTPP_ANTHROPIC_API_KEY in htpp-digital-twin/.env "
            "(Anthropic Console → API keys). Claude Code login is not used by the API."
        )
    import anthropic

    headers = {}
    wid = workspace_id()
    if wid:
        headers["anthropic-workspace-id"] = wid
    return anthropic.Anthropic(api_key=key, default_headers=headers or None)


def chat(messages: list[dict[str, str]], *, include_insights: bool = False) -> dict[str, Any]:
    client = _client()
    if not workspace_id():
        # Multi-workspace keys fail without the header; fail early with a clear fix.
        raise ClaudeConfigError(
            "This Anthropic key needs a workspace. In Console open Settings → Workspaces, "
            "copy the workspace id (wrkspc_...), and set HTPP_ANTHROPIC_WORKSPACE_ID in .env. "
            "Or create a new API key that is scoped to one workspace."
        )
    briefing = plant_briefing()
    user_block = (
        "Plant briefing (JSON from DuckDB):\n"
        f"{briefing_text(briefing)}\n\n"
        "Conversation:\n"
        + "\n".join(f"{m['role'].upper()}: {m['content']}" for m in messages[-12:])
    )
    response = client.messages.create(
        model=settings.anthropic_model,
        max_tokens=900,
        system=SYSTEM,
        messages=[{"role": "user", "content": user_block}],
    )
    text = "".join(block.text for block in response.content if getattr(block, "type", "") == "text")
    result: dict[str, Any] = {
        "reply": text.strip(),
        "model": settings.anthropic_model,
        "usage": {
            "input_tokens": getattr(response.usage, "input_tokens", None),
            "output_tokens": getattr(response.usage, "output_tokens", None),
        },
    }
    if include_insights:
        result["insights"] = rule_insights(briefing)
    return result


def insights_payload() -> dict[str, Any]:
    briefing = plant_briefing()
    payload: dict[str, Any] = {
        "insights": rule_insights(briefing),
        "claude_configured": bool(api_key()) and bool(workspace_id()),
        "claude_needs_workspace": bool(api_key()) and not bool(workspace_id()),
        "generated_at": briefing["generated_at"],
    }
    if not api_key() or not workspace_id():
        return payload
    try:
        result = chat(
            [{"role": "user", "content": (
                "Write one short plant brief (2–4 sentences) for a non-technical supervisor. "
                "Use reactor names R1/R2/R3. No ISO timestamps, no JSON keys, no p10/p90 or ingest jargon. "
                "Say what is running well and what needs attention."
            )}],
        )
        payload["claude_summary"] = result["reply"]
    except Exception as exc:  # noqa: BLE001
        payload["claude_error"] = str(exc)
    return payload
