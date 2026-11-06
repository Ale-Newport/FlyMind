import { useEffect, useMemo, useRef } from "react";
import { Canvas, type ThreeEvent, useThree } from "@react-three/fiber";
import { GizmoHelper, Html, OrbitControls, OrthographicCamera, PerspectiveCamera } from "@react-three/drei";
import * as THREE from "three";
import type { OrbitControls as OrbitImpl } from "three-stdlib";
import { useChartColors } from "../lib/colors";

// Dataset coordinates (FlyWire FAFB, nm -> um): +x = fly right, +y = ventral, +z = posterior.
// Display: X = x (fly right), Y = -y (dorsal up), Z = -z (anterior toward +Z).
export function toDisplay(x: number, y: number, z: number, c: [number, number, number]): [number, number, number] {
  return [x - c[0], -(y - c[1]), -(z - c[2])];
}

const vert = /* glsl */ `
  attribute vec3 color;
  attribute float aAlpha;
  attribute float aSize;
  uniform float uSize;
  uniform float uScale;
  uniform float uOrtho;
  varying vec3 vColor;
  varying float vAlpha;
  void main() {
    vColor = color;
    vAlpha = aAlpha;
    vec4 mv = modelViewMatrix * vec4(position, 1.0);
    gl_Position = projectionMatrix * mv;
    float s = uSize * aSize;
    gl_PointSize = uOrtho > 0.5 ? s * uScale : s * uScale / -mv.z;
    if (aAlpha <= 0.0) gl_PointSize = 0.0;
  }
`;
const frag = /* glsl */ `
  varying vec3 vColor;
  varying float vAlpha;
  void main() {
    vec2 d = gl_PointCoord - 0.5;
    float r = dot(d, d);
    if (r > 0.25) discard;
    float edge = smoothstep(0.25, 0.16, r);
    gl_FragColor = vec4(vColor, vAlpha * edge);
  }
`;

export interface PointStyle {
  colors: Float32Array; // rgb per point
  alpha: Float32Array; // per point (0 = hidden)
  size: Float32Array; // per point multiplier
}

function Points({ positions, style, pointSize, ortho, onPick, radius }: {
  positions: Float32Array;
  style: PointStyle;
  pointSize: number;
  ortho: boolean;
  onPick: (idx: number) => void;
  radius: number;
}) {
  const geom = useMemo(() => {
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.BufferAttribute(positions, 3));
    g.setAttribute("color", new THREE.BufferAttribute(style.colors, 3));
    g.setAttribute("aAlpha", new THREE.BufferAttribute(style.alpha, 1));
    g.setAttribute("aSize", new THREE.BufferAttribute(style.size, 1));
    g.computeBoundingSphere();
    return g;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [positions]);
  useEffect(() => {
    (geom.getAttribute("color") as THREE.BufferAttribute).array.set(style.colors);
    (geom.getAttribute("aAlpha") as THREE.BufferAttribute).array.set(style.alpha);
    (geom.getAttribute("aSize") as THREE.BufferAttribute).array.set(style.size);
    geom.getAttribute("color").needsUpdate = true;
    geom.getAttribute("aAlpha").needsUpdate = true;
    geom.getAttribute("aSize").needsUpdate = true;
  }, [geom, style]);
  const mat = useMemo(() => new THREE.ShaderMaterial({
    vertexShader: vert, fragmentShader: frag, transparent: true, depthWrite: false,
    uniforms: { uSize: { value: pointSize }, uScale: { value: 1 }, uOrtho: { value: 0 } },
  }), []);  // eslint-disable-line react-hooks/exhaustive-deps
  const { size } = useThree();
  useEffect(() => {
    // perspective: size ~ pointSize px at the default viewing distance (2.2 R)
    mat.uniforms.uSize.value = pointSize;
    mat.uniforms.uScale.value = ortho ? 1.0 * (size.height / 900) : radius * 2.2 * (size.height / 900);
    mat.uniforms.uOrtho.value = ortho ? 1 : 0;
  }, [mat, pointSize, ortho, radius, size.height]);
  const onDown = (e: ThreeEvent<PointerEvent>) => {
    // nearest visible intersected point
    const hits = e.intersections.filter((h) => h.index !== undefined && style.alpha[h.index!] > 0.05);
    if (hits.length) {
      e.stopPropagation();
      onPick(hits[0].index!);
    }
  };
  return <points geometry={geom} material={mat} onPointerDown={onDown} frustumCulled={false} />;
}

function Skeletons({ segments }: { segments: { positions: Float32Array; color: string }[] }) {
  return (
    <>
      {segments.map((s, i) => (
        <lineSegments key={i} frustumCulled={false}>
          <bufferGeometry>
            <bufferAttribute attach="attributes-position" args={[s.positions, 3]} />
          </bufferGeometry>
          <lineBasicMaterial color={s.color} transparent opacity={0.95} />
        </lineSegments>
      ))}
    </>
  );
}

function CameraRig({ controls, focus, resetKey, radius }: {
  controls: React.RefObject<OrbitImpl | null>;
  focus: [number, number, number] | null;
  resetKey: number;
  radius: number;
}) {
  const { camera } = useThree();
  useEffect(() => {
    const c = controls.current;
    if (!c) return;
    camera.position.set(0, 0, radius * 2.2);
    c.target.set(0, 0, 0);
    if ((camera as THREE.OrthographicCamera).isOrthographicCamera) (camera as THREE.OrthographicCamera).zoom = 1;
    camera.updateProjectionMatrix();
    c.update();
  }, [resetKey, camera, controls, radius]);
  useEffect(() => {
    const c = controls.current;
    if (!c || !focus) return;
    // smooth transition of the orbit target to the focus point
    const start = c.target.clone();
    const end = new THREE.Vector3(...focus);
    let t = 0;
    let raf = 0;
    const tick = () => {
      t = Math.min(1, t + 0.06);
      const k = 1 - Math.pow(1 - t, 3);
      c.target.lerpVectors(start, end, k);
      c.update();
      if (t < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [focus, controls]);
  return null;
}

function AxisLabel({ position, text, color }: { position: [number, number, number]; text: string; color: string }) {
  return <Html position={position} center><span style={{ color, fontSize: 11, fontWeight: 700 }}>{text}</span></Html>;
}

function OrientationGizmo({ axis: ax }: { axis: { x: string; y: string; z: string } }) {
  // Anatomical axes: +X fly right, +Y dorsal, +Z anterior.
  const arm = (dir: [number, number, number], color: string) => (
    <mesh position={dir.map((v) => v * 0.5) as [number, number, number]} rotation={dir[0] ? [0, 0, -Math.PI / 2] : dir[2] ? [Math.PI / 2, 0, 0] : [0, 0, 0]}>
      <cylinderGeometry args={[0.04, 0.04, 1, 8]} />
      <meshBasicMaterial color={color} />
    </mesh>
  );
  return (
    <group scale={40}>
      {arm([1, 0, 0], ax.x)}
      {arm([0, 1, 0], ax.y)}
      {arm([0, 0, 1], ax.z)}
      <AxisLabel position={[1.25, 0, 0]} text="R" color={ax.x} />
      <AxisLabel position={[0, 1.25, 0]} text="D" color={ax.y} />
      <AxisLabel position={[0, 0, 1.25]} text="A" color={ax.z} />
    </group>
  );
}

export function BrainScene({ positions, style, pointSize, ortho, onPick, labels, skeletons, focus, resetKey, radius }: {
  positions: Float32Array;
  style: PointStyle;
  pointSize: number;
  ortho: boolean;
  onPick: (idx: number) => void;
  labels: { text: string; pos: [number, number, number] }[];
  skeletons: { positions: Float32Array; color: string }[];
  focus: [number, number, number] | null;
  resetKey: number;
  radius: number;
}) {
  const controls = useRef<OrbitImpl | null>(null);
  // Points use normal (alpha) blending, never additive, so they stay visible on the light theme's background.
  const { scene } = useChartColors();
  return (
    <Canvas dpr={[1, 2]} gl={{ antialias: true, preserveDrawingBuffer: true }} raycaster={{ params: { Points: { threshold: radius / 250 } } as THREE.RaycasterParameters }} data-testid="brain-canvas">
      <color key={scene.bg} attach="background" args={[scene.bg]} />
      {ortho ? (
        <OrthographicCamera makeDefault position={[0, 0, radius * 2.2]} near={-radius * 10} far={radius * 10} zoom={1} left={-radius * 1.2} right={radius * 1.2} top={radius * 0.75} bottom={-radius * 0.75} />
      ) : (
        <PerspectiveCamera makeDefault position={[0, 0, radius * 2.2]} fov={40} near={radius / 200} far={radius * 20} />
      )}
      <OrbitControls ref={controls} makeDefault enableDamping dampingFactor={0.12} />
      <CameraRig controls={controls} focus={focus} resetKey={resetKey} radius={radius} />
      <Points positions={positions} style={style} pointSize={pointSize} ortho={ortho} onPick={onPick} radius={radius} />
      <Skeletons segments={skeletons} />
      {labels.map((l) => (
        <Html key={l.text} position={l.pos} center zIndexRange={[10, 0]}>
          <span className="pointer-events-none select-none whitespace-nowrap rounded-[3px] bg-ink-950/75 px-1 text-[10px] font-medium text-ink-300">{l.text}</span>
        </Html>
      ))}
      <GizmoHelper alignment="bottom-left" margin={[70, 70]}>
        <OrientationGizmo axis={scene.axis} />
      </GizmoHelper>
    </Canvas>
  );
}
