import { useMemo, useRef } from "react";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { Grid, OrbitControls } from "@react-three/drei";
import * as THREE from "three";
import type { OrbitControls as OrbitImpl } from "three-stdlib";
import type { MeshMeta, SceneObject } from "../lib/types";

/** Geometry of the official NeuroMechFly meshes, built once from the server mesh pack. */
export function buildFlyGeometries(meta: MeshMeta, data: ArrayBuffer) {
  return meta.geoms.map((g) => {
    const verts = new Float32Array(data, g.vertex_offset, g.n_vertices * 3);
    const faces = new Uint32Array(data, g.face_offset, g.n_faces * 3);
    const geom = new THREE.BufferGeometry();
    geom.setAttribute("position", new THREE.BufferAttribute(verts.slice(), 3));
    geom.setIndex(new THREE.BufferAttribute(faces.slice(), 1));
    geom.computeVertexNormals();
    const [r, gg, b, a] = g.rgba;
    const mat = new THREE.MeshStandardMaterial({
      color: new THREE.Color(r, gg, b), roughness: 0.55, metalness: 0.05,
      transparent: a < 0.99 || g.name.includes("wing"), opacity: g.name.includes("wing") ? 0.45 : a,
      side: g.name.includes("wing") ? THREE.DoubleSide : THREE.FrontSide,
    });
    return { name: g.name, geom, mat };
  });
}

export interface PoseSource {
  /** flat [x, y, z, qw, qx, qy, qz] per geom (MuJoCo world frame, mm) */
  poses: Float32Array | number[] | null;
  pos: number[] | null;
}

function Fly({ parts, source }: { parts: ReturnType<typeof buildFlyGeometries>; source: React.RefObject<PoseSource> }) {
  const refs = useRef<(THREE.Mesh | null)[]>([]);
  const q = useMemo(() => new THREE.Quaternion(), []);
  useFrame(() => {
    const p = source.current?.poses;
    if (!p) return;
    for (let i = 0; i < parts.length; i++) {
      const m = refs.current[i];
      if (!m) continue;
      const o = i * 7;
      m.position.set(p[o], p[o + 1], p[o + 2]);
      q.set(p[o + 4], p[o + 5], p[o + 6], p[o + 3]);
      m.quaternion.copy(q);
    }
  });
  return (
    <group>
      {parts.map((pt, i) => (
        <mesh key={pt.name} ref={(el) => { refs.current[i] = el; }} geometry={pt.geom} material={pt.mat} castShadow />
      ))}
    </group>
  );
}

function Objects({ objects }: { objects: SceneObject[] }) {
  return (
    <>
      {objects.map((o) => {
        const quat = new THREE.Quaternion(o.quat[1], o.quat[2], o.quat[3], o.quat[0]);
        const color = new THREE.Color(o.rgba[0], o.rgba[1], o.rgba[2]);
        if (o.type === "box") {
          return (
            <mesh key={o.name} position={o.pos as [number, number, number]} quaternion={quat} castShadow receiveShadow>
              <boxGeometry args={[o.size[0] * 2, o.size[1] * 2, o.size[2] * 2]} />
              <meshStandardMaterial color={color} roughness={0.8} />
            </mesh>
          );
        }
        if (o.type === "cylinder") {
          const emissive = o.kind === "light";
          return (
            <mesh key={o.name} position={o.pos as [number, number, number]} rotation={[Math.PI / 2, 0, 0]}>
              <cylinderGeometry args={[o.size[0], o.size[0], o.size[1] * 2, 32]} />
              <meshStandardMaterial color={color} emissive={emissive ? color : undefined} emissiveIntensity={emissive ? 1.2 : 0} transparent={!emissive} opacity={emissive ? 1 : 0.9} />
            </mesh>
          );
        }
        return (
          <mesh key={o.name} position={o.pos as [number, number, number]}>
            <sphereGeometry args={[o.size[0], 16, 16]} />
            <meshBasicMaterial color={color} transparent opacity={0.7} />
          </mesh>
        );
      })}
    </>
  );
}

function OdorHeatmap({ field }: { field: { x_mm: number[]; y_mm: number[]; attractive: number[][]; aversive: number[][] } | null }) {
  const tex = useMemo(() => {
    if (!field) return null;
    const n = field.x_mm.length;
    const data = new Uint8Array(n * n * 4);
    for (let j = 0; j < n; j++) for (let i = 0; i < n; i++) {
      const a = Math.min(1, field.attractive[j][i]);
      const v = Math.min(1, field.aversive[j][i]);
      const k = 4 * (j * n + i);
      data[k] = 255 * v; data[k + 1] = 220 * a; data[k + 2] = 120 * a; data[k + 3] = 200 * Math.max(a, v);
    }
    const t = new THREE.DataTexture(data, n, n);
    t.needsUpdate = true;
    t.magFilter = THREE.LinearFilter;
    return t;
  }, [field]);
  if (!field || !tex) return null;
  const x0 = field.x_mm[0], x1 = field.x_mm[field.x_mm.length - 1];
  const y0 = field.y_mm[0], y1 = field.y_mm[field.y_mm.length - 1];
  return (
    <mesh position={[(x0 + x1) / 2, (y0 + y1) / 2, 0.01]}>
      <planeGeometry args={[x1 - x0, y1 - y0]} />
      <meshBasicMaterial map={tex} transparent depthWrite={false} />
    </mesh>
  );
}

function Trail({ points }: { points: number[][] }) {
  const geom = useMemo(() => {
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.BufferAttribute(new Float32Array(points.flatMap((p) => [p[0], p[1], 0.03])), 3));
    return g;
  }, [points]);
  return (
    <line>
      <primitive object={geom} attach="geometry" />
      <lineBasicMaterial color="#5eead4" />
    </line>
  );
}

function Follow({ source, follow, controls }: { source: React.RefObject<PoseSource>; follow: boolean; controls: React.RefObject<OrbitImpl | null> }) {
  const { camera } = useThree();
  const last = useRef<THREE.Vector3 | null>(null);
  useFrame(() => {
    const c = controls.current;
    const pos = source.current?.pos;
    if (!c || !pos) return;
    // pos is MuJoCo (z-up); scene is rotated so world = (x, z, -y)
    const target = new THREE.Vector3(pos[0], pos[2], -pos[1]);
    if (follow) {
      if (last.current) camera.position.add(target.clone().sub(last.current));
      c.target.copy(target);
      c.update();
    }
    last.current = target;
  });
  return null;
}

export function FlyScene({ parts, source, objects, odor, trail, follow, ambient }: {
  parts: ReturnType<typeof buildFlyGeometries> | null;
  source: React.RefObject<PoseSource>;
  objects: SceneObject[];
  odor: Parameters<typeof OdorHeatmap>[0]["field"];
  trail: number[][];
  follow: boolean;
  ambient: number;
}) {
  const controls = useRef<OrbitImpl | null>(null);
  return (
    <Canvas shadows dpr={[1, 2]} camera={{ position: [-8, 6, 8], fov: 40, near: 0.05, far: 2000 }} gl={{ preserveDrawingBuffer: true }} data-testid="fly-canvas">
      <color attach="background" args={[ambient < 0.3 ? "#04060c" : "#0b1020"]} />
      <hemisphereLight args={["#cfd8ff", "#1a1d29", 0.35 + ambient * 0.6]} />
      <directionalLight position={[10, 25, 10]} intensity={0.4 + ambient * 1.2} castShadow shadow-mapSize={[1024, 1024]} />
      <OrbitControls ref={controls} makeDefault enableDamping />
      <Follow source={source} follow={follow} controls={controls} />
      {/* MuJoCo is z-up (mm); rotate into three.js y-up */}
      <group rotation={[-Math.PI / 2, 0, 0]}>
        <mesh receiveShadow>
          <planeGeometry args={[400, 400]} />
          <meshStandardMaterial color={ambient < 0.3 ? "#0d0f16" : "#151b2c"} roughness={1} />
        </mesh>
        <OdorHeatmap field={odor} />
        <Objects objects={objects} />
        {trail.length > 1 && <Trail points={trail} />}
        {parts && <Fly parts={parts} source={source} />}
      </group>
      <Grid position={[0, 0.005, 0]} args={[200, 200]} cellSize={1} cellColor="#1f2944" sectionSize={10} sectionColor="#2c3859" fadeDistance={120} infiniteGrid />
    </Canvas>
  );
}
