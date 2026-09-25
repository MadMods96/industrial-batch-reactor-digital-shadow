"""Assistant chat and insight routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from htpp.assistant.claude import ClaudeConfigError, chat, insights_payload

router = APIRouter()


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1)
    include_insights: bool = False


@router.get("/assistant/insights")
def insights() -> dict:
    try:
        return insights_payload()
    except Exception as exc:  # noqa: BLE001
        return {
            "insights": [{
                "severity": "warning",
                "title": "Assistant briefing unavailable",
                "detail": str(exc),
            }],
            "claude_configured": False,
            "claude_error": str(exc),
        }


@router.post("/assistant/chat")
def assistant_chat(body: ChatRequest) -> dict:
    cleaned = [{"role": m.role, "content": m.content} for m in body.messages if m.content.strip()]
    if not cleaned:
        raise HTTPException(status_code=422, detail={"error": {"code": "empty", "message": "No message", "detail": None}})
    try:
        return chat(cleaned, include_insights=body.include_insights)
    except ClaudeConfigError as exc:
        raise HTTPException(
            status_code=503,
            detail={"error": {"code": "claude_not_configured", "message": str(exc), "detail": None}},
        ) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=502,
            detail={"error": {"code": "claude_error", "message": str(exc), "detail": None}},
        ) from exc
