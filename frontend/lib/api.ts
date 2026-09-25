export const API = process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000";

function camel(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(camel);
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value as Record<string, unknown>).map(([key, inner]) => [
        key.replace(/_([a-z0-9])/g, (_, c: string) => c.toUpperCase()),
        camel(inner),
      ]),
    );
  }
  return value;
}

export async function apiGet<T>(path: string): Promise<T> {
  const response = await fetch(`${API}${path}`, { cache: "no-store" });
  if (!response.ok) throw new Error(`${response.status} ${API}${path}`);
  return camel(await response.json()) as T;
}

export async function apiPost<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(`${API}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    const raw = await response.text();
    try {
      const parsed = JSON.parse(raw);
      const message = parsed?.detail?.error?.message || parsed?.error?.message || raw;
      throw new Error(message);
    } catch (err) {
      if (err instanceof Error && err.message !== raw) throw err;
      throw new Error(raw);
    }
  }
  return camel(await response.json()) as T;
}
