import * as THREE from "three";

const STOPS = [
  { t: 100, h: 205, s: 0.08, l: 0.22, i: 0 },
  { t: 200, h: 8, s: 0.45, l: 0.18, i: 0.05 },
  { t: 300, h: 4, s: 0.72, l: 0.28, i: 0.2 },
  { t: 400, h: 2, s: 0.84, l: 0.38, i: 0.5 },
  { t: 450, h: 18, s: 0.9, l: 0.46, i: 0.75 },
  { t: 500, h: 28, s: 0.92, l: 0.5, i: 1 },
  { t: 600, h: 36, s: 0.95, l: 0.55, i: 1.4 },
  { t: 700, h: 46, s: 0.95, l: 0.6, i: 1.8 },
];

const BASE = new THREE.Color("#9aa4ab");

function hsl(h: number, s: number, l: number, target: THREE.Color) {
  target.setHSL(h / 360, s, l);
  return target;
}

export function tempToShell(trC: number, emissive: THREE.Color, base: THREE.Color) {
  base.copy(BASE);
  if (trC <= STOPS[0].t) {
    hsl(STOPS[0].h, STOPS[0].s, STOPS[0].l, emissive);
    return { emissiveIntensity: STOPS[0].i };
  }
  const last = STOPS[STOPS.length - 1];
  if (trC >= last.t) {
    hsl(last.h, last.s, last.l, emissive);
    return { emissiveIntensity: last.i };
  }
  let i = 0;
  while (STOPS[i + 1].t < trC) i += 1;
  const a = STOPS[i];
  const b = STOPS[i + 1];
  const u = (trC - a.t) / (b.t - a.t);
  hsl(a.h + (b.h - a.h) * u, a.s + (b.s - a.s) * u, a.l + (b.l - a.l) * u, emissive);
  return { emissiveIntensity: a.i + (b.i - a.i) * u };
}

export function tempToCss(trC: number): string {
  const emissive = new THREE.Color();
  const base = new THREE.Color();
  tempToShell(trC, emissive, base);
  return `#${emissive.getHexString()}`;
}
