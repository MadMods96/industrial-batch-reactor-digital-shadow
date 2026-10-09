/**
 * Real digital shadow API (FastAPI). No same-origin Next mock routes.
 */
export function apiBase(): string {
  const raw = process.env.NEXT_PUBLIC_API_BASE_URL;
  if (typeof raw === "string" && raw.trim()) {
    return raw.replace(/\/$/, "");
  }
  return "http://127.0.0.1:8000";
}

export function wsUrl(): string {
  const raw = process.env.NEXT_PUBLIC_WS_URL;
  if (typeof raw === "string" && raw.trim()) {
    return raw;
  }
  return "ws://127.0.0.1:8000/ws/live";
}
