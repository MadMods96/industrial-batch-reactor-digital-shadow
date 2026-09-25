import { NextResponse } from "next/server";
import { ASSISTANT_SYSTEM, demoBriefing } from "@/lib/demo/plant";

export const dynamic = "force-dynamic";

type Msg = { role: string; content: string };

export async function POST(req: Request) {
  const key = (process.env.HTPP_ANTHROPIC_API_KEY || process.env.ANTHROPIC_API_KEY || "").trim();
  const workspace = (process.env.HTPP_ANTHROPIC_WORKSPACE_ID || process.env.ANTHROPIC_WORKSPACE_ID || "").trim();
  const model = process.env.HTPP_ANTHROPIC_MODEL || "claude-sonnet-4-5";

  if (!key) {
    return NextResponse.json(
      { error: { code: "claude_not_configured", message: "Set HTPP_ANTHROPIC_API_KEY in Vercel env." } },
      { status: 503 },
    );
  }
  if (!workspace) {
    return NextResponse.json(
      {
        error: {
          code: "claude_not_configured",
          message: "Set HTPP_ANTHROPIC_WORKSPACE_ID (wrkspc_…) in Vercel env.",
        },
      },
      { status: 503 },
    );
  }

  let body: { messages?: Msg[] };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: { message: "Invalid JSON" } }, { status: 400 });
  }
  const messages = (body.messages || []).filter((m) => m.content?.trim()).slice(-12);
  if (!messages.length) {
    return NextResponse.json({ error: { message: "No message" } }, { status: 422 });
  }

  const briefing = demoBriefing();
  const userBlock =
    `Plant briefing (JSON):\n${JSON.stringify(briefing, null, 2)}\n\nConversation:\n` +
    messages.map((m) => `${m.role.toUpperCase()}: ${m.content}`).join("\n");

  const anthropicRes = await fetch("https://api.anthropic.com/v1/messages", {
    method: "POST",
    headers: {
      "content-type": "application/json",
      "x-api-key": key,
      "anthropic-version": "2023-06-01",
      "anthropic-workspace-id": workspace,
    },
    body: JSON.stringify({
      model,
      max_tokens: 900,
      system: ASSISTANT_SYSTEM,
      messages: [{ role: "user", content: userBlock }],
    }),
  });

  const raw = await anthropicRes.text();
  if (!anthropicRes.ok) {
    let message = raw;
    try {
      message = JSON.parse(raw)?.error?.message || raw;
    } catch {
      /* keep */
    }
    return NextResponse.json(
      { error: { code: "claude_error", message: String(message) } },
      { status: 502 },
    );
  }

  const parsed = JSON.parse(raw) as {
    content?: Array<{ type: string; text?: string }>;
    usage?: { input_tokens?: number; output_tokens?: number };
  };
  const reply = (parsed.content || [])
    .filter((b) => b.type === "text" && b.text)
    .map((b) => b.text)
    .join("\n")
    .trim();

  return NextResponse.json({
    reply,
    model,
    usage: {
      input_tokens: parsed.usage?.input_tokens ?? null,
      output_tokens: parsed.usage?.output_tokens ?? null,
    },
  });
}
