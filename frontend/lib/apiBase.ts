/**
 * Empty / "same" → same-origin (Vercel Next `/api`).
 * On *.vercel.app with no env, also same-origin.
 * Local default remains the FastAPI port.
 */
export function apiBase(): string {
  const raw = process.env.NEXT_PUBLIC_API_BASE_URL;
  if (raw === "" || raw === "same") return "";
  if (typeof raw === "string" && raw.trim()) {
    return raw.replace(/\/$/, "");
  }
  if (typeof window !== "undefined" && /\.vercel\.app$/i.test(window.location.hostname)) {
    return "";
  }
  return "http://127.0.0.1:8000";
}

export function wsUrl(): string | null {
  const raw = process.env.NEXT_PUBLIC_WS_URL;
  if (raw === "" || raw === "poll" || raw === "same") return null;
  if (typeof raw === "string" && raw.trim()) {
    if (/vercel\.app/i.test(raw)) return null;
    return raw;
  }
  if (typeof window !== "undefined" && /\.vercel\.app$/i.test(window.location.hostname)) {
    return null;
  }
  return "ws://127.0.0.1:8000/ws/live";
}
