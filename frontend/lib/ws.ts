"use client";

import { apiBase, wsUrl } from "./apiBase";
import { useLive } from "./store";

let started = false;

export function connectLive() {
  if (started || typeof window === "undefined") return;
  started = true;

  const socketUrl = wsUrl();
  if (!socketUrl) {
    void pollSnapshot();
    window.setInterval(() => {
      void pollSnapshot();
    }, 4000);
    return;
  }

  let delay = 1000;
  const open = () => {
    const socket = new WebSocket(socketUrl);
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

async function pollSnapshot() {
  try {
    const response = await fetch(`${apiBase()}/api/live/snapshot`, { cache: "no-store" });
    if (!response.ok) throw new Error(String(response.status));
    const payload = await response.json();
    useLive.getState().applyMessage(payload);
  } catch {
    useLive.getState().setStatus("down");
  }
}
