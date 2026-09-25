"use client";

import { OrbitControls } from "@react-three/drei";
import { Canvas, useFrame } from "@react-three/fiber";
import { EffectComposer, Bloom } from "@react-three/postprocessing";
import { useMemo, useRef } from "react";
import * as THREE from "three";
import { useLive } from "@/lib/store";
import { ReactorPlaceholder } from "./ReactorPlaceholder";

const IDS = [1093, 1094, 1146];
const SPACING = 11;

type ControlsApi = {
  target: THREE.Vector3;
  object: THREE.Camera;
  update: () => void;
  enabled: boolean;
};

function framing(mode: string, desired: THREE.Vector3, look: THREE.Vector3) {
  const slot =
    mode === "reactor-1094" ? 1 :
    mode === "reactor-1146" ? 2 :
    mode === "reactor-1093" || mode === "cutaway" ? 0 : -1;

  if (slot < 0) {
    // Wide overview: all three kilns centered, room to orbit.
    desired.set(0, 9.2, 26);
    look.set(0, 1.35, 0);
    return;
  }
  const x = (slot - 1) * SPACING;
  if (mode === "cutaway") {
    desired.set(x + 0.2, 2.0, 2.2);
    look.set(x, 1.45, 0.4);
    return;
  }
  desired.set(x + 4.2, 2.8, 6.5);
  look.set(x, 1.45, 0.4);
}

function Rig() {
  const controls = useRef<ControlsApi | null>(null);
  const desired = useMemo(() => new THREE.Vector3(), []);
  const look = useMemo(() => new THREE.Vector3(), []);
  const lastTick = useRef(-1);
  const flying = useRef(true);
  const userOrbit = useRef(false);

  useFrame((_, dt) => {
    const { camera: mode, cameraTick } = useLive.getState();
    if (cameraTick !== lastTick.current) {
      lastTick.current = cameraTick;
      userOrbit.current = false;
      flying.current = true;
      framing(mode, desired, look);
    }
    const api = controls.current;
    const cam = api?.object;
    if (!api || !cam || !flying.current || userOrbit.current) return;

    const k = 1 - Math.exp(-dt * 3.6);
    cam.position.lerp(desired, k);
    api.target.lerp(look, k);
    api.update();

    if (cam.position.distanceTo(desired) < 0.08 && api.target.distanceTo(look) < 0.08) {
      cam.position.copy(desired);
      api.target.copy(look);
      flying.current = false;
    }
  });

  return (
    <OrbitControls
      ref={controls as never}
      makeDefault
      enablePan
      enableRotate
      enableZoom
      maxPolarAngle={Math.PI / 2.02}
      minDistance={4}
      maxDistance={48}
      dampingFactor={0.08}
      enableDamping
      onStart={() => {
        userOrbit.current = true;
        flying.current = false;
      }}
    />
  );
}

function Floor() {
  return (
    <group>
      <mesh rotation={[-Math.PI / 2, 0, 0]} receiveShadow position={[0, 0, 0]}>
        <planeGeometry args={[72, 30]} />
        <meshStandardMaterial color="#d7e0e7" metalness={0.08} roughness={0.92} />
      </mesh>
      {Array.from({ length: 20 }).map((_, i) => (
        <mesh key={i} position={[-30 + i * 3.2, 0.012, 0]} rotation={[-Math.PI / 2, 0, 0]}>
          <planeGeometry args={[0.04, 22]} />
          <meshBasicMaterial color="#9aafbd" transparent opacity={0.22} />
        </mesh>
      ))}
      {/* Bay markers only — no center “selected” ring in All view */}
      {[-1, 0, 1].map((slot) => (
        <mesh key={slot} position={[slot * SPACING, 0.013, 0]} rotation={[-Math.PI / 2, 0, 0]} scale={[1, 1.55, 1]}>
          <ringGeometry args={[2.0, 2.08, 48]} />
          <meshBasicMaterial color="#7d93a2" transparent opacity={0.32} />
        </mesh>
      ))}
    </group>
  );
}

export function PlantScene() {
  const post = useLive((s) => s.post);
  return (
    <Canvas
      shadows
      camera={{ position: [0, 9.2, 26], fov: 40, near: 0.1, far: 140 }}
      dpr={[1, 1.5]}
      gl={{ antialias: true }}
    >
      <color attach="background" args={["#e4ecf2"]} />
      <fog attach="fog" args={["#e4ecf2", 36, 90]} />
      <hemisphereLight args={["#ffffff", "#b7c5d0", 0.95]} />
      <directionalLight
        position={[8, 16, 10]}
        intensity={1.85}
        castShadow
        shadow-mapSize-width={2048}
        shadow-mapSize-height={2048}
      />
      <directionalLight position={[-10, 8, -6]} intensity={0.45} color="#cfe0ea" />
      <ambientLight intensity={0.55} />
      <Floor />
      {IDS.map((id, slot) => (
        <ReactorPlaceholder key={id} machineId={id} position={[(slot - 1) * SPACING, 0, 0]} />
      ))}
      <Rig />
      {post && (
        <EffectComposer>
          <Bloom luminanceThreshold={0.78} intensity={0.28} mipmapBlur />
        </EffectComposer>
      )}
    </Canvas>
  );
}
