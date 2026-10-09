"use client";

import { wsUrl } from "./apiBase";
import { useLive } from "./store";

let started = false;

export function connectLive() {
  if (started || typeof window === "undefined") return;
  started = true;

  const socketUrl = wsUrl();
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
    socket.onerror = () => {
      useLive.getState().setStatus("down");
    };
    window.setInterval(() => {
      if (socket.readyState === WebSocket.OPEN) socket.send(JSON.stringify({ type: "ping" }));
    }, 20000);
  };

  open();
}
