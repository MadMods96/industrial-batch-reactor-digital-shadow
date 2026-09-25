"use client";

import { useLive } from "./store";

const WS = process.env.NEXT_PUBLIC_WS_URL || "ws://127.0.0.1:8000/ws/live";
let started = false;

export function connectLive() {
  if (started || typeof window === "undefined") return;
  started = true;
  let delay = 1000;
  const open = () => {
    const socket = new WebSocket(WS);
    socket.onopen = () => {
      delay = 1000;
      useLive.getState().setStatus("live");
    };
    socket.onmessage = (event) => {
      useLive.getState().applyMessage(JSON.parse(event.data));
    };
    socket.onclose = () => {
      useLive.getState().setStatus("down");
      window.setTimeout(open, delay);
      delay = Math.min(delay * 2, 30000);
    };
    window.setInterval(() => {
      if (socket.readyState === WebSocket.OPEN) socket.send(JSON.stringify({ type: "ping" }));
    }, 20000);
  };
  open();
}

export const API = process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000";

export async function apiGet<T>(path: string): Promise<T> {
  const response = await fetch(`${API}${path}`);
  if (!response.ok) throw new Error(`${response.status} ${path}`);
  return response.json() as Promise<T>;
}

export async function apiPost<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(`${API}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) throw new Error(`${response.status} ${path}`);
  return response.json() as Promise<T>;
}
