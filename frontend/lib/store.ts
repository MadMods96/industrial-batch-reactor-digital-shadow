"use client";

import { create } from "zustand";

export type Dense = {
  stepS: number;
  horizonS: number;
  trC: number[];
  tsC: number[];
  prBar: number[];
  psBar: number[];
  processState: string[];
};

export type MachineLive = {
  machineId: number;
  displayName: string;
  sceneSlot: number;
  online: boolean;
  lastSampleAt: string | null;
  stalenessS: number;
  batchNo: number | null;
  batchElapsedMin: number | null;
  processState: string;
  processRaw: string | null;
  faultState: string;
  phaseElapsedMin: number | null;
  measured: {
    trC: number | null;
    tsC: number | null;
    prBar: number | null;
    psBar: number | null;
    ambTempC: number | null;
    rohCPerMin: number | null;
  };
  interpolationMode: "model" | "linear_fallback";
  dense: Dense;
  residual: { rTC: number | null; severity: string; alarm: boolean } | null;
  projection: {
    predictedEndAt: string | null;
    predictedTotalDurationMin: number | null;
    predictedYields: {
      oilYieldPct: { p10: number; p50: number; p90: number };
    } | null;
  };
  anchorMs: number;
  blendFromTr: number | null;
  blendUntil: number;
  doorSeen: boolean;
};

type Alarm = { id: string; machineId: number; severity: string; message: string; at: string };

type Store = {
  status: "connecting" | "live" | "down";
  modelVersion: string | null;
  serverTime: string | null;
  machines: Record<number, MachineLive>;
  alarms: Alarm[];
  camera: string;
  cameraTick: number;
  post: boolean;
  setCamera: (camera: string) => void;
  setPost: (post: boolean) => void;
  setStatus: (status: Store["status"]) => void;
  applyMessage: (raw: Record<string, unknown>) => void;
  dismiss: (id: string) => void;
};

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

export const useLive = create<Store>((set, get) => ({
  status: "connecting",
  modelVersion: null,
  serverTime: null,
  machines: {},
  alarms: [],
  camera: "overview",
  cameraTick: 0,
  post: true,
  setCamera: (camera) => set((s) => ({ camera, cameraTick: s.cameraTick + 1 })),
  setPost: (post) => set({ post }),
  setStatus: (status) => set({ status }),
  dismiss: (id) => set({ alarms: get().alarms.filter((a) => a.id !== id) }),
  applyMessage: (raw) => {
    const msg = camel(raw) as {
      type: string;
      modelVersion?: string;
      serverTime?: string;
      machines?: MachineLive[];
      machineId?: number;
      severity?: string;
      message?: string;
      detectedAt?: string;
    };
    if (msg.type === "alarm") {
      set({
        alarms: [
          {
            id: `${msg.machineId}-${msg.detectedAt}`,
            machineId: msg.machineId ?? 0,
            severity: msg.severity ?? "warning",
            message: msg.message ?? "Alarm",
            at: msg.detectedAt ?? "",
          },
          ...get().alarms,
        ].slice(0, 6),
      });
      return;
    }
    const now = performance.now();
    const prev = get().machines;
    const next: Record<number, MachineLive> = { ...prev };
    for (const machine of msg.machines ?? []) {
      const old = prev[machine.machineId];
      const measured = machine.measured?.trC ?? old?.blendFromTr ?? null;
      next[machine.machineId] = {
        ...machine,
        displayName: machine.displayName || `Reactor ${machine.machineId}`,
        anchorMs: now,
        blendFromTr: old ? sampleTr(old, now) : measured,
        blendUntil: old ? now + 400 : 0,
        doorSeen: old?.doorSeen ?? false,
      };
    }
    set({
      machines: next,
      modelVersion: msg.modelVersion ?? get().modelVersion,
      serverTime: msg.serverTime ?? null,
      status: "live",
    });
  },
}));

export function sampleTr(machine: MachineLive, now: number): number {
  const sampled = sampleMachine(machine, now);
  return sampled.tr;
}

export function sampleMachine(machine: MachineLive, now: number) {
  const stale = machine.stalenessS > 600 || machine.online === false;
  // Prefer measured for HUD cards (Fix Brief 003 F1). Dense is only a hold buffer.
  const tr = machine.measured.trC ?? 0;
  const ts = machine.measured.tsC ?? 0;
  const pr = machine.measured.prBar ?? 0;
  const ps = machine.measured.psBar ?? 0;
  return {
    tr,
    ts,
    pr,
    ps,
    process: machine.processState,
    fault: machine.faultState,
    stale,
    roh: machine.measured.rohCPerMin ?? 0,
  };
}
