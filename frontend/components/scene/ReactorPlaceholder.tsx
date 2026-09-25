"use client";

import { useMemo, useRef } from "react";
import { useFrame } from "@react-three/fiber";
import * as THREE from "three";
import { sampleMachine, useLive, type MachineLive } from "@/lib/store";
import { stackToneFor, visualFor } from "./stateMapping";
import { tempToShell } from "./tempRamp";

const STEEL = "#c5ced4";
const STEEL_DARK = "#8a959e";
const STEEL_LIGHT = "#e4ebf0";
const RIB = "#aab4bc";
const ACCENT_YELLOW = "#f0c12e";
const BLUE = "#2f6fb5";

const SEGMENTS = 6;
const BODY_LEN = 5.2;
const BODY_R = 1.05;
const BODY_Y = 1.55;

function LugRing({ radius, z, count = 22 }: { radius: number; z: number; count?: number }) {
  return (
    <group position={[0, 0, z]}>
      {Array.from({ length: count }).map((_, i) => {
        const a = (i / count) * Math.PI * 2;
        return (
          <mesh
            key={i}
            position={[Math.cos(a) * radius, Math.sin(a) * radius, 0.04]}
            rotation={[0, 0, a]}
          >
            <boxGeometry args={[0.11, 0.09, 0.1]} />
            <meshStandardMaterial color={STEEL_DARK} metalness={0.75} roughness={0.4} />
          </mesh>
        );
      })}
    </group>
  );
}

function BoltRing({ radius, z, count = 12 }: { radius: number; z: number; count?: number }) {
  return (
    <group position={[0, 0, z]}>
      {Array.from({ length: count }).map((_, i) => {
        const a = (i / count) * Math.PI * 2;
        return (
          <mesh key={i} position={[Math.cos(a) * radius, Math.sin(a) * radius, 0]} rotation={[Math.PI / 2, 0, 0]}>
            <cylinderGeometry args={[0.035, 0.035, 0.06, 8]} />
            <meshStandardMaterial color={STEEL_LIGHT} metalness={0.95} roughness={0.22} />
          </mesh>
        );
      })}
    </group>
  );
}

export function ReactorPlaceholder({ machineId, position }: { machineId: number; position: [number, number, number] }) {
  const door = useRef<THREE.Group>(null);
  const chute = useRef<THREE.Group>(null);
  const shell = useRef<THREE.MeshStandardMaterial>(null);
  const interior = useRef<THREE.MeshStandardMaterial>(null);
  const sep = useRef<THREE.MeshStandardMaterial>(null);
  const flame = useRef<THREE.Mesh>(null);
  const gas = useRef<THREE.Mesh>(null);
  const n2 = useRef<THREE.Mesh>(null);
  const beacon = useRef<THREE.Mesh>(null);
  const outlet = useRef<THREE.MeshStandardMaterial>(null);
  const passage = useRef<THREE.MeshStandardMaterial>(null);
  const badge = useRef<THREE.MeshStandardMaterial>(null);
  const solenoid = useRef<THREE.MeshStandardMaterial>(null);
  const bin = useRef<THREE.Mesh>(null);
  const needlePr = useRef<THREE.Group>(null);
  const hydraulic = useRef<THREE.Mesh>(null);
  const stackMats = useRef<(THREE.MeshStandardMaterial | null)[]>([]);
  const doorOpen = useRef(0);
  const chuteOpen = useRef(0);
  const seen = useRef(false);
  const emissive = useMemo(() => new THREE.Color(), []);
  const base = useMemo(() => new THREE.Color(), []);
  const sepEmissive = useMemo(() => new THREE.Color(), []);
  const reduced = useMemo(() => typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches, []);

  const segLen = BODY_LEN / SEGMENTS;
  const bodyZ0 = -BODY_LEN / 2;

  useFrame(({ clock }) => {
    const machine = useLive.getState().machines[machineId];
    if (!machine) return;
    const now = performance.now();
    const sample = sampleMachine(machine, now);
    const visual = visualFor(sample.process);
    const t = clock.elapsedTime;
    const targetDoor = visual.door;
    if (!seen.current) {
      doorOpen.current = targetDoor;
      seen.current = true;
      machine.doorSeen = true;
    } else {
      // ~1.8s full swing so open/close reads clearly
      const step = Math.min(1 / 110, Math.abs(targetDoor - doorOpen.current));
      doorOpen.current += Math.sign(targetDoor - doorOpen.current) * step;
    }
    if (door.current) {
      // Real kiln door swings ~170° left on side hinges
      door.current.rotation.y = doorOpen.current * (Math.PI * 0.94);
    }
    if (hydraulic.current) {
      hydraulic.current.scale.y = 0.7 + doorOpen.current * 0.55;
      hydraulic.current.rotation.z = -0.15 - doorOpen.current * 0.75;
    }
    const chuteTarget = visual.chute;
    chuteOpen.current += (chuteTarget - chuteOpen.current) * 0.05;
    if (chute.current) chute.current.rotation.x = -chuteOpen.current * 0.9;
    if (shell.current) {
      if (visual.shellRamp) {
        const look = tempToShell(sample.tr, emissive, base);
        shell.current.color.copy(base);
        shell.current.emissive.copy(emissive);
        shell.current.emissiveIntensity = sample.stale ? look.emissiveIntensity * 0.15 : look.emissiveIntensity;
      } else {
        shell.current.color.set(STEEL);
        shell.current.emissive.set("#d7dee3");
        shell.current.emissiveIntensity = 0.06;
      }
    }
    if (interior.current) {
      tempToShell(sample.tr, emissive, base);
      interior.current.emissive.copy(emissive);
      interior.current.emissiveIntensity = doorOpen.current > 0.15 ? 0.35 + doorOpen.current * 1.1 : 0.04;
      interior.current.opacity = 1;
    }
    if (sep.current) {
      const look = tempToShell(sample.ts, sepEmissive, base);
      sep.current.emissive.copy(sepEmissive);
      sep.current.emissiveIntensity = look.emissiveIntensity * 0.7;
    }
    const roh = Math.max(0, sample.roh);
    const flameScale = visual.flame * (sample.process === "heating" ? 0.45 + Math.min(roh, 4) * 0.2 : 0.7);
    const afterglow = sample.process === "cooling" ? Math.max(0, 1 - (now % 4000) / 4000) * 0.3 : 0;
    if (flame.current) {
      const flicker = 0.85 + Math.sin(t * 17.0) * 0.08 + Math.sin(t * 9.0) * 0.05;
      flame.current.scale.set(1, Math.max(0.02, (flameScale + afterglow) * flicker), 1);
      (flame.current.material as THREE.MeshBasicMaterial).opacity = Math.min(1, flameScale + afterglow);
    }
    if (gas.current) {
      const choke = sample.fault === "gas_passage_choke";
      const speed = choke ? (Math.sin(t * 8) > 0 ? 0.15 : 0.9) : 0.35 + Math.min(Math.abs(sample.pr) * 2, 1.2);
      gas.current.position.z = bodyZ0 + 0.4 + ((t * speed) % 1) * (BODY_LEN - 0.8);
      gas.current.visible = visual.gasFlow > 0;
      if (choke) gas.current.position.z = Math.min(gas.current.position.z, bodyZ0 + BODY_LEN * 0.35);
    }
    if (n2.current) {
      n2.current.visible = visual.n2Flow > 0;
      n2.current.position.z = -0.4 + ((t * 0.6) % 1) * 1.4;
    }
    if (solenoid.current) {
      solenoid.current.emissive.set(visual.solenoid ? "#e0a15a" : "#222");
      solenoid.current.emissiveIntensity = visual.solenoid ? 0.5 + Math.sin(t * 6) * 0.4 : 0;
    }
    const strobe = reduced ? 1 : 0.5 + 0.5 * Math.sin(t * Math.PI * 2 * 2);
    if (outlet.current) {
      const on = sample.fault === "choke_emergency";
      outlet.current.emissive.set("#e23b4a");
      outlet.current.emissiveIntensity = on ? strobe * 2 : 0;
    }
    if (passage.current) {
      const on = sample.fault === "gas_passage_choke";
      passage.current.emissive.set("#e07a3d");
      passage.current.emissiveIntensity = on ? strobe * 1.6 : visual.gasFlow * 0.25;
    }
    if (badge.current) {
      const on = sample.fault === "pressure_sensor_error";
      badge.current.emissive.set("#e23b4a");
      badge.current.emissiveIntensity = on ? (reduced ? 1 : strobe) : 0;
      badge.current.color.set(on ? "#e23b4a" : "#9aa7b0");
    }
    if (beacon.current) {
      const alarm = sample.fault !== "none" && sample.fault !== "pressure_sensor_error";
      beacon.current.visible = false;
      beacon.current.rotation.y += alarm && !reduced ? 0.08 : 0;
      (beacon.current.material as THREE.MeshBasicMaterial).color.set(sample.fault === "unknown_fault" ? "#d946ef" : "#e23b4a");
    }
    const tone = stackToneFor(sample.process, sample.fault, sample.stale);
    const bands: Array<"red" | "amber" | "green" | "blue"> = ["red", "amber", "green", "blue"];
    const lit = {
      red: "#ff2d3a",
      amber: "#ff9a1f",
      green: "#22c55e",
      blue: "#2f6fff",
    } as const;
    const dim = {
      red: "#6b1a22",
      amber: "#6b4a1a",
      green: "#1a4a2e",
      blue: "#1a2e5a",
    } as const;
    for (let i = 0; i < 4; i++) {
      const mat = stackMats.current[i];
      if (!mat) continue;
      const key = bands[i];
      const on = tone === key;
      const pulse = on && key === "red" && !reduced ? 0.65 + 0.35 * Math.sin(t * Math.PI * 4) : 1;
      mat.color.set(on ? lit[key] : dim[key]);
      mat.emissive.set(on ? lit[key] : "#000000");
      mat.emissiveIntensity = on ? 1.35 * pulse : 0.05;
      mat.opacity = on ? 0.95 : 0.55;
    }
    if (needlePr.current) {
      const limp = sample.fault === "pressure_sensor_error";
      needlePr.current.rotation.z = limp ? 0 : -0.6 + Math.max(-0.2, Math.min(1.2, sample.pr)) * 1.4;
    }
    if (bin.current) {
      const fill = visual.chute ? Math.min(1, (machine.phaseElapsedMin ?? 0) / 170) : 0.05;
      bin.current.scale.y = 0.05 + fill * 0.9;
      bin.current.position.y = 0.15 + bin.current.scale.y * 0.35;
    }
  });

  return (
    <group name="Reactor" position={position}>
      {/* Cradle / skid base */}
      <group name="Frame">
        <mesh name="Skid" position={[0, 0.12, 0]} receiveShadow>
          <boxGeometry args={[3.1, 0.22, BODY_LEN + 0.9]} />
          <meshStandardMaterial color="#d8dde2" metalness={0.35} roughness={0.55} />
        </mesh>
        {[-1.8, -0.6, 0.6, 1.8].map((z) => (
          <mesh key={z} position={[0, 0.55, z]}>
            <boxGeometry args={[2.55, 0.16, 0.28]} />
            <meshStandardMaterial color="#b7c0c7" metalness={0.45} roughness={0.48} />
          </mesh>
        ))}
        {[-1.05, 1.05].map((x) =>
          [-2.2, 0, 2.2].map((z) => (
            <mesh key={`${x}-${z}`} position={[x, 0.78, z]}>
              <boxGeometry args={[0.18, 0.55, 0.22]} />
              <meshStandardMaterial color="#9aa4ad" metalness={0.5} roughness={0.45} />
            </mesh>
          )),
        )}
      </group>

      {/* Horizontal rotary kiln body — axis along Z, door faces camera */}
      <group name="Vessel" position={[0, BODY_Y, 0]}>
        <mesh name="Vessel_Shell" rotation={[Math.PI / 2, 0, 0]} castShadow>
          <cylinderGeometry args={[BODY_R, BODY_R, BODY_LEN, 40]} />
          <meshStandardMaterial
            ref={shell}
            color={STEEL}
            metalness={0.78}
            roughness={0.32}
            emissive="#cfd6db"
            emissiveIntensity={0.05}
          />
        </mesh>
        {Array.from({ length: SEGMENTS - 1 }).map((_, i) => (
          <mesh key={i} position={[0, 0, bodyZ0 + segLen * (i + 1)]} rotation={[Math.PI / 2, 0, 0]}>
            <cylinderGeometry args={[BODY_R + 0.07, BODY_R + 0.07, 0.11, 36]} />
            <meshStandardMaterial color={RIB} metalness={0.7} roughness={0.4} />
          </mesh>
        ))}

        {/* Rear end cap */}
        <mesh position={[0, 0, bodyZ0 - 0.06]} rotation={[Math.PI / 2, 0, 0]}>
          <cylinderGeometry args={[BODY_R + 0.04, BODY_R + 0.04, 0.12, 36]} />
          <meshStandardMaterial color={STEEL_DARK} metalness={0.8} roughness={0.35} />
        </mesh>

        {/* Fixed sealing flange + locking lugs (stay when door opens) */}
        <mesh position={[0, 0, BODY_LEN / 2 + 0.02]} rotation={[Math.PI / 2, 0, 0]}>
          <cylinderGeometry args={[BODY_R + 0.1, BODY_R + 0.1, 0.12, 48]} />
          <meshStandardMaterial color={STEEL_DARK} metalness={0.78} roughness={0.35} />
        </mesh>
        <mesh position={[0, 0, BODY_LEN / 2 + 0.02]} rotation={[Math.PI / 2, 0, 0]}>
          <cylinderGeometry args={[BODY_R - 0.02, BODY_R - 0.02, 0.14, 40]} />
          <meshStandardMaterial color="#1c1814" metalness={0.15} roughness={0.95} />
        </mesh>
        <LugRing radius={BODY_R + 0.02} z={BODY_LEN / 2 + 0.06} count={22} />

        {/* Deep kiln mouth — visible when door is open */}
        <mesh position={[0, 0, BODY_LEN / 2 - 0.9]} rotation={[Math.PI / 2, 0, 0]}>
          <cylinderGeometry args={[BODY_R - 0.1, BODY_R - 0.1, 1.7, 32, 1, true]} />
          <meshStandardMaterial color="#14110e" metalness={0.05} roughness={1} side={THREE.BackSide} />
        </mesh>
        <mesh position={[0, 0, BODY_LEN / 2 - 1.4]}>
          <sphereGeometry args={[0.5, 16, 12]} />
          <meshStandardMaterial ref={interior} color="#24160e" emissive="#ff6a22" emissiveIntensity={0.05} roughness={1} />
        </mesh>
      </group>

      {/* Door hinged on left — swings open like the plant photo */}
      <group name="Door_Hinge" ref={door} position={[-(BODY_R + 0.12), BODY_Y, BODY_LEN / 2 + 0.12]}>
        {[0.72, 0.28, -0.28, -0.72].map((y) => (
          <mesh key={y} position={[0, y, 0]} rotation={[0, 0, Math.PI / 2]}>
            <cylinderGeometry args={[0.07, 0.07, 0.22, 12]} />
            <meshStandardMaterial color={STEEL_LIGHT} metalness={0.9} roughness={0.25} />
          </mesh>
        ))}

        <group name="Door" position={[BODY_R + 0.12, 0, 0]}>
          <mesh name="Door_Plate" rotation={[Math.PI / 2, 0, 0]} castShadow>
            <cylinderGeometry args={[BODY_R + 0.04, BODY_R + 0.04, 0.16, 48]} />
            <meshStandardMaterial color={STEEL} metalness={0.8} roughness={0.3} />
          </mesh>

          <mesh name="Door_Hinge_Frame" position={[-(BODY_R - 0.15), 0, 0.02]}>
            <boxGeometry args={[0.28, BODY_R * 1.7, 0.12]} />
            <meshStandardMaterial color={STEEL_DARK} metalness={0.7} roughness={0.4} />
          </mesh>

          {/* Center inspection hatch */}
          <mesh name="Hatch" position={[0, 0.05, 0.1]} rotation={[Math.PI / 2, 0, 0]}>
            <cylinderGeometry args={[0.32, 0.32, 0.1, 28]} />
            <meshStandardMaterial color={STEEL_LIGHT} metalness={0.85} roughness={0.28} />
          </mesh>
          <BoltRing radius={0.26} z={0.16} count={12} />
          <mesh position={[0, 0.05, 0.16]} rotation={[Math.PI / 2, 0, 0]}>
            <cylinderGeometry args={[0.1, 0.1, 0.04, 16]} />
            <meshStandardMaterial color={STEEL_DARK} metalness={0.85} roughness={0.3} />
          </mesh>
          <mesh position={[-0.38, 0.05, 0.14]}>
            <boxGeometry args={[0.12, 0.05, 0.05]} />
            <meshStandardMaterial color={STEEL_DARK} metalness={0.7} roughness={0.35} />
          </mesh>

          <mesh position={[0, -0.55, 0.1]} rotation={[Math.PI / 2, 0, 0]}>
            <cylinderGeometry args={[0.14, 0.14, 0.08, 16]} />
            <meshStandardMaterial color={STEEL_DARK} metalness={0.75} roughness={0.35} />
          </mesh>
          <mesh position={[0, -0.42, 0.12]}>
            <cylinderGeometry args={[0.03, 0.03, 0.2, 8]} />
            <meshStandardMaterial color={STEEL_LIGHT} metalness={0.8} roughness={0.3} />
          </mesh>

          {/* Inner reinforcement visible when open */}
          <mesh position={[0, 0, -0.1]}>
            <boxGeometry args={[0.55, 0.14, 0.08]} />
            <meshStandardMaterial color={STEEL_DARK} metalness={0.65} roughness={0.45} />
          </mesh>
          <mesh position={[0, 0, -0.1]}>
            <boxGeometry args={[0.14, 0.55, 0.08]} />
            <meshStandardMaterial color={STEEL_DARK} metalness={0.65} roughness={0.45} />
          </mesh>
        </group>
      </group>

      <group name="Door_Brace" position={[-(BODY_R + 0.45), BODY_Y + 0.15, BODY_LEN / 2 - 0.2]}>
        <mesh ref={hydraulic} rotation={[0, 0, -0.2]}>
          <cylinderGeometry args={[0.04, 0.05, 0.7, 8]} />
          <meshStandardMaterial color={STEEL_DARK} metalness={0.7} roughness={0.35} />
        </mesh>
      </group>

      {/* Top gas manifold + risers */}
      <group name="Piping">
        <mesh
          name="Pipe_Gas_Header"
          position={[0, BODY_Y + BODY_R + 0.35, 0]}
          rotation={[Math.PI / 2, 0, 0]}
        >
          <cylinderGeometry args={[0.11, 0.11, BODY_LEN * 0.92, 12]} />
          <meshStandardMaterial ref={passage} color={STEEL_DARK} emissive="#000" metalness={0.75} roughness={0.32} />
        </mesh>
        {Array.from({ length: SEGMENTS }).map((_, i) => {
          const z = bodyZ0 + segLen * (i + 0.5);
          return (
            <mesh key={i} position={[0, BODY_Y + BODY_R + 0.12, z]}>
              <cylinderGeometry args={[0.06, 0.06, 0.45, 8]} />
              <meshStandardMaterial color={STEEL_DARK} metalness={0.7} roughness={0.35} />
            </mesh>
          );
        })}
        <mesh name="Valve_Solenoid" position={[0.2, BODY_Y + BODY_R + 0.55, BODY_LEN * 0.15]}>
          <boxGeometry args={[0.22, 0.22, 0.22]} />
          <meshStandardMaterial ref={solenoid} color="#303840" emissive="#000" />
        </mesh>
        <mesh ref={gas} position={[0, BODY_Y + BODY_R + 0.5, 0]}>
          <sphereGeometry args={[0.06, 8, 8]} />
          <meshBasicMaterial color="#ffcf8a" />
        </mesh>
        <mesh
          name="Pipe_N2_Line"
          position={[-BODY_R - 0.2, BODY_Y - 0.15, 0]}
          rotation={[Math.PI / 2, 0, 0]}
        >
          <cylinderGeometry args={[0.045, 0.045, BODY_LEN * 0.7, 8]} />
          <meshStandardMaterial color="#7f97b8" metalness={0.6} roughness={0.3} />
        </mesh>
        <mesh ref={n2} position={[-BODY_R - 0.2, BODY_Y - 0.15, -0.5]}>
          <sphereGeometry args={[0.06, 8, 8]} />
          <meshBasicMaterial color="#d7f4ff" transparent opacity={0.85} />
        </mesh>
        <mesh name="Pipe_Gas_Outlet" position={[0.55, BODY_Y + BODY_R + 0.55, -BODY_LEN * 0.35]}>
          <cylinderGeometry args={[0.07, 0.07, 0.55, 8]} />
          <meshStandardMaterial ref={outlet} color={STEEL_DARK} emissive="#000" />
        </mesh>
      </group>

      {/* Yellow side utility / guard rails */}
      <group name="Yellow_Rails">
        {[-1, 1].map((side) => (
          <group key={side}>
            <mesh position={[side * (BODY_R + 0.28), BODY_Y - 0.05, 0]} rotation={[Math.PI / 2, 0, 0]}>
              <cylinderGeometry args={[0.035, 0.035, BODY_LEN * 0.88, 8]} />
              <meshStandardMaterial color={ACCENT_YELLOW} metalness={0.35} roughness={0.4} />
            </mesh>
            <mesh position={[side * (BODY_R + 0.28), BODY_Y + 0.35, 0]} rotation={[Math.PI / 2, 0, 0]}>
              <cylinderGeometry args={[0.03, 0.03, BODY_LEN * 0.88, 8]} />
              <meshStandardMaterial color={ACCENT_YELLOW} metalness={0.35} roughness={0.4} />
            </mesh>
            {[-1.8, -0.6, 0.6, 1.8].map((z) => (
              <mesh key={z} position={[side * (BODY_R + 0.28), BODY_Y + 0.15, z]}>
                <cylinderGeometry args={[0.025, 0.025, 0.45, 6]} />
                <meshStandardMaterial color={ACCENT_YELLOW} metalness={0.35} roughness={0.4} />
              </mesh>
            ))}
          </group>
        ))}
      </group>

      {/* Blue blower / burner skid (front-left like photo) */}
      <group name="Burner" position={[-1.55, 0.45, BODY_LEN / 2 - 0.4]}>
        <mesh>
          <boxGeometry args={[0.85, 0.55, 0.7]} />
          <meshStandardMaterial color={BLUE} metalness={0.4} roughness={0.45} />
        </mesh>
        <mesh position={[0, 0.45, 0]} rotation={[0, 0, Math.PI / 2]}>
          <cylinderGeometry args={[0.22, 0.22, 0.35, 16]} />
          <meshStandardMaterial color="#245a96" metalness={0.5} roughness={0.4} />
        </mesh>
        <mesh name="Burner_Nozzle" position={[0.55, 0.15, 0.15]} rotation={[0, 0, Math.PI / 2]}>
          <cylinderGeometry args={[0.08, 0.12, 0.35, 10]} />
          <meshStandardMaterial color="#3a434a" metalness={0.7} roughness={0.35} />
        </mesh>
        <group name="Burner_Flame_Anchor" position={[0.85, 0.15, 0.15]}>
          <mesh ref={flame} position={[0.2, 0, 0]} rotation={[0, 0, -Math.PI / 2]}>
            <coneGeometry args={[0.12, 0.55, 10]} />
            <meshBasicMaterial color="#ffb15a" transparent opacity={0.9} />
          </mesh>
        </group>
      </group>

      {/* Oil separator + condenser (plant train, side of kiln) */}
      <group name="Separator" position={[2.35, 0, -0.4]}>
        <mesh name="Separator_Shell" position={[0, 1.2, 0]}>
          <cylinderGeometry args={[0.42, 0.48, 1.9, 20]} />
          <meshStandardMaterial ref={sep} color="#7a858d" metalness={0.75} roughness={0.4} />
        </mesh>
        <mesh name="Separator_Supports" position={[0, 0.22, 0]}>
          <boxGeometry args={[0.65, 0.35, 0.65]} />
          <meshStandardMaterial color="#9aa4ad" metalness={0.4} roughness={0.5} />
        </mesh>
        <mesh
          name="Pipe_Separator_Link"
          position={[-0.9, BODY_Y + 0.55, 0.2]}
          rotation={[0, 0, Math.PI / 2]}
        >
          <cylinderGeometry args={[0.055, 0.055, 1.4, 8]} />
          <meshStandardMaterial color={STEEL_DARK} metalness={0.7} roughness={0.35} />
        </mesh>
      </group>
      <group name="Condenser" position={[3.55, 0.95, -0.5]}>
        <mesh name="Condenser_Body">
          <boxGeometry args={[0.65, 0.85, 0.65]} />
          <meshStandardMaterial color="#5a6a74" metalness={0.55} roughness={0.35} />
        </mesh>
        <mesh name="Condenser_Coils" rotation={[Math.PI / 2, 0, 0]}>
          <torusGeometry args={[0.24, 0.045, 8, 16]} />
          <meshStandardMaterial color="#8fd0c8" emissive="#1a4a44" emissiveIntensity={0.35} metalness={0.4} />
        </mesh>
      </group>

      {/* Carbon discharge at rear */}
      <group name="Discharge" position={[0, 0.35, bodyZ0 - 0.55]}>
        <group name="Discharge_Chute_Hinge" ref={chute} position={[0, 0.55, 0]}>
          <mesh name="Discharge_Chute" position={[0, -0.25, -0.2]} rotation={[0.45, 0, 0]}>
            <boxGeometry args={[0.5, 0.55, 0.28]} />
            <meshStandardMaterial color="#6a757e" metalness={0.5} roughness={0.45} />
          </mesh>
        </group>
        <group name="Carbon_Bin" position={[0, 0, -0.55]}>
          <mesh>
            <boxGeometry args={[0.75, 0.5, 0.7]} />
            <meshStandardMaterial color="#4a545c" metalness={0.35} roughness={0.55} />
          </mesh>
          <mesh name="Carbon_Bin_Fill" ref={bin} position={[0, 0.2, 0]}>
            <boxGeometry args={[0.55, 0.7, 0.55]} />
            <meshStandardMaterial color="#1a1a1a" roughness={1} />
          </mesh>
        </group>
      </group>

      <group name="Instruments" position={[0.95, BODY_Y + 0.35, BODY_LEN / 2 + 0.05]}>
        <group name="Gauge_Pressure_Reactor">
          <mesh>
            <circleGeometry args={[0.14, 16]} />
            <meshStandardMaterial color="#dfe6ea" />
          </mesh>
          <group name="Gauge_Needle_Pr" ref={needlePr}>
            <mesh position={[0.05, 0, 0.01]}>
              <boxGeometry args={[0.1, 0.014, 0.01]} />
              <meshBasicMaterial color="#111" />
            </mesh>
          </group>
        </group>
        <mesh name="Sensor_Badge_Pressure" position={[-0.35, -0.25, 0]}>
          <boxGeometry args={[0.12, 0.08, 0.02]} />
          <meshStandardMaterial ref={badge} color="#9aa7b0" emissive="#000" />
        </mesh>
        <mesh name="Beacon_Light" ref={beacon} position={[0.35, 0.55, -0.2]} visible={false}>
          <sphereGeometry args={[0.09, 12, 12]} />
          <meshBasicMaterial color="#e23b4a" />
        </mesh>
      </group>

      {/* Plant stack light — red / amber / green / blue */}
      <group name="Stack_Light" position={[BODY_R + 0.55, 0, BODY_LEN / 2 - 0.35]}>
        <mesh position={[0, 1.55, 0]}>
          <cylinderGeometry args={[0.035, 0.035, 3.1, 10]} />
          <meshStandardMaterial color="#cfd6db" metalness={0.7} roughness={0.35} />
        </mesh>
        <mesh position={[0, 3.15, 0]}>
          <cylinderGeometry args={[0.1, 0.11, 0.14, 16]} />
          <meshStandardMaterial color="#d8dde2" metalness={0.4} roughness={0.5} />
        </mesh>
        {(
          [
            { y: 3.95, color: "#6b1a22", key: "red" },
            { y: 3.7, color: "#6b4a1a", key: "amber" },
            { y: 3.45, color: "#1a4a2e", key: "green" },
            { y: 3.2, color: "#1a2e5a", key: "blue" },
          ] as const
        ).map((band, i) => (
          <group key={band.key}>
            <mesh position={[0, band.y, 0]}>
              <cylinderGeometry args={[0.13, 0.13, 0.22, 20]} />
              <meshStandardMaterial
                ref={(m) => {
                  stackMats.current[i] = m;
                }}
                color={band.color}
                emissive="#000000"
                emissiveIntensity={0.05}
                transparent
                opacity={0.55}
                roughness={0.35}
                metalness={0.05}
              />
            </mesh>
            <mesh position={[0, band.y + 0.12, 0]}>
              <cylinderGeometry args={[0.135, 0.135, 0.03, 16]} />
              <meshStandardMaterial color={STEEL_LIGHT} metalness={0.9} roughness={0.25} />
            </mesh>
          </group>
        ))}
      </group>

      <group name="HUD_Anchor" position={[0, 3.2, 0]} />
    </group>
  );
}

export function focusSlot(slot: number): [number, number, number] {
  return [(slot - 1) * 14, 2.0, 10];
}

void (null as unknown as MachineLive);
