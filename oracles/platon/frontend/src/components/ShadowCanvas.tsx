import { useMemo, useRef, type MutableRefObject } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import { Float, Line, OrbitControls, Sparkles, Stars } from "@react-three/drei";
import {
  Bloom,
  ChromaticAberration,
  EffectComposer,
  Vignette,
} from "@react-three/postprocessing";
import { BlendFunction } from "postprocessing";
import * as THREE from "three";
import type { Telemetry } from "../lib/types";
import {
  N_OSCILLATORS,
  SPHERE_RADIUS,
  fibonacciDirection,
  phaseColor,
} from "../lib/types";

const R = SPHERE_RADIUS;

function spherePos(index: number, amp: number): [number, number, number] {
  const [dx, dy, dz] = fibonacciDirection(index);
  const s = R * (1 + amp * 0.16);
  return [dx * s, dy * s, dz * s];
}

type LiveDynamics = {
  amps: Float64Array;
  phases: Float64Array;
  order: number;
  kappa: number;
  projX: number;
  projY: number;
  theta1: number;
  theta2: number;
};

function useLiveDynamics(telemetry: Telemetry | null) {
  const demo = useMemo(() => {
    const r = new Float64Array(N_OSCILLATORS);
    const th = new Float64Array(N_OSCILLATORS);
    const omega = new Float64Array(N_OSCILLATORS);
    for (let i = 0; i < N_OSCILLATORS; i++) {
      r[i] = 0.35 + Math.random() * 0.55;
      th[i] = Math.random() * Math.PI * 2;
      omega[i] = 0.8 + (i / (N_OSCILLATORS - 1)) * 1.6;
    }
    return { r, th, omega };
  }, []);

  const live = useRef<LiveDynamics>({
    amps: demo.r,
    phases: demo.th,
    order: 0.45,
    kappa: 0.4,
    projX: 0,
    projY: 0,
    theta1: 0.7,
    theta2: 1.1,
  });

  useFrame(({ clock }, delta) => {
    const t = clock.elapsedTime;
    const dt = Math.min(0.033, delta);
    const L = live.current;

    if (telemetry) {
      L.amps = telemetry.oscillators.amplitudes as unknown as Float64Array;
      L.phases = telemetry.oscillators.phases as unknown as Float64Array;
      L.order = telemetry.order_parameter;
      L.kappa = telemetry.kappa;
      L.projX = telemetry.projection.x;
      L.projY = telemetry.projection.y;
      L.theta1 = telemetry.projection_angles.theta1;
      L.theta2 = telemetry.projection_angles.theta2;
    } else {
      const { r, th, omega } = demo;
      L.kappa = 0.55 + 0.35 * Math.sin(t * 0.25);
      let sx = 0;
      let sy = 0;
      for (let i = 0; i < N_OSCILLATORS; i++) {
        sx += Math.cos(th[i]);
        sy += Math.sin(th[i]);
      }
      const meanPhase = Math.atan2(sy, sx);
      L.order = Math.hypot(sx, sy) / N_OSCILLATORS;
      for (let i = 0; i < N_OSCILLATORS; i++) {
        r[i] += dt * r[i] * (1 - r[i] * r[i]);
        if (r[i] < 0.02) r[i] = 0.02;
        th[i] += dt * (omega[i] + L.kappa * Math.sin(meanPhase - th[i]));
      }
      L.amps = r;
      L.phases = th;
      L.theta1 = t * 0.28;
      L.theta2 = t * 0.19 + 1.1;
      let px = 0;
      let py = 0;
      for (let i = 0; i < N_OSCILLATORS; i++) {
        px += r[i] * Math.cos(th[i] + L.theta1);
        py += r[i] * Math.sin(th[i] + L.theta2);
      }
      const sc = Math.max(Math.hypot(px, py), 1e-6);
      L.projX = px / sc;
      L.projY = py / sc;
    }
  });

  return live;
}

function phaseHue(phase: number): THREE.Color {
  return new THREE.Color(phaseColor(phase, 0.8));
}

function AgentBeams({ invokes }: { invokes: import("../lib/types").AgentInvoke[] }) {
  const now = Date.now() / 1000;
  const recent = invokes.filter((i) => now - i.timestamp < 8);
  return (
    <group>
      {recent.map((inv, idx) => {
        const age = now - inv.timestamp;
        const fade = Math.max(0, 1 - age / 8);
        const color = inv.is_prediction ? "#c084fc" : "#6ee7ff";
        const target: [number, number, number] = [
          (idx % 5) * 1.2 - 2.4,
          2.5 + (idx % 3) * 0.3,
          ((idx * 2) % 5) * 1.1 - 2.2,
        ];
        return (
          <Line
            key={`${inv.timestamp}-${idx}`}
            points={[
              new THREE.Vector3(0, 9, -6),
              new THREE.Vector3(...target),
            ]}
            color={color}
            transparent
            opacity={0.15 + fade * 0.55}
            lineWidth={inv.is_prediction ? 2 : 1}
          />
        );
      })}
    </group>
  );
}

function DreamTrajectories({
  preview,
}: {
  preview: import("../lib/types").DreamPreview | null;
}) {
  if (!preview) return null;
  const surrPts = preview.surrogate.map(
    (p) => new THREE.Vector3(p.x * 4, 0.6, p.y * 4)
  );
  const truthPts = preview.truth.map(
    (p) => new THREE.Vector3(p.x * 4, 0.9, p.y * 4)
  );
  return (
    <group>
      <Line points={surrPts} color="#f472b6" transparent opacity={0.7} lineWidth={2} />
      <Line points={truthPts} color="#6ee7ff" transparent opacity={0.85} lineWidth={2} />
    </group>
  );
}

function CouplingWeb({ live }: { live: MutableRefObject<LiveDynamics> }) {
  const linesRef = useRef<THREE.LineSegments>(null);
  const geom = useMemo(() => {
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.BufferAttribute(new Float32Array(32 * 32 * 2 * 3), 3));
    return g;
  }, []);
  const mat = useMemo(
    () =>
      new THREE.LineBasicMaterial({
        color: "#6ee7ff",
        transparent: true,
        opacity: 0.24,
        blending: THREE.AdditiveBlending,
        depthWrite: false,
      }),
    []
  );

  useFrame(() => {
    const { amps, phases } = live.current;
    const arr = geom.attributes.position.array as Float32Array;
    let seg = 0;
    for (let i = 0; i < N_OSCILLATORS; i++) {
      for (let j = i + 1; j < N_OSCILLATORS; j++) {
        const dp = Math.abs(phases[i] - phases[j]);
        const diff = Math.min(dp, Math.PI * 2 - dp);
        if (diff < 0.55 && amps[i] > 0.24 && amps[j] > 0.24) {
          const a = spherePos(i, amps[i]);
          const b = spherePos(j, amps[j]);
          arr[seg * 6] = a[0];
          arr[seg * 6 + 1] = a[1];
          arr[seg * 6 + 2] = a[2];
          arr[seg * 6 + 3] = b[0];
          arr[seg * 6 + 4] = b[1];
          arr[seg * 6 + 5] = b[2];
          seg++;
        }
      }
    }
    geom.setDrawRange(0, seg * 2);
    geom.attributes.position.needsUpdate = true;
  });

  return <lineSegments ref={linesRef} geometry={geom} material={mat} frustumCulled={false} />;
}

function OscillatorNode({
  index,
  live,
}: {
  index: number;
  live: MutableRefObject<LiveDynamics>;
}) {
  const root = useRef<THREE.Group>(null);
  const mesh = useRef<THREE.Mesh>(null);
  const glow = useRef<THREE.Mesh>(null);
  const bodyMat = useRef<THREE.MeshPhysicalMaterial>(null);

  useFrame(({ clock }) => {
    if (!root.current || !mesh.current || !glow.current) return;
    const { amps, phases } = live.current;
    const amp = amps[index];
    const phase = phases[index];
    const [x, y, z] = spherePos(index, amp);
    root.current.position.set(x, y, z);

    const color = phaseHue(phase);
    if (bodyMat.current) {
      bodyMat.current.color.copy(color);
      bodyMat.current.emissive.copy(color);
      bodyMat.current.emissiveIntensity = 0.9 + amp * 1.7;
    }
    const glowMat = glow.current.material as THREE.MeshBasicMaterial;
    glowMat.color.copy(color);

    const t = clock.elapsedTime;
    const pulse = 1 + Math.sin(t * 2.8 + phase + index * 0.2) * 0.12 * amp;
    mesh.current.scale.setScalar(pulse);
    glow.current.scale.setScalar(pulse * (1.5 + amp * 0.5));
    glowMat.opacity = 0.06 + amp * 0.14;
  });

  return (
    <group ref={root}>
      <mesh ref={glow}>
        <sphereGeometry args={[0.42, 20, 20]} />
        <meshBasicMaterial color="#6ee7ff" transparent opacity={0.15} blending={THREE.AdditiveBlending} />
      </mesh>
      <Float speed={1.2} rotationIntensity={0.18} floatIntensity={0.42}>
        <mesh ref={mesh}>
          <sphereGeometry args={[0.14, 48, 48]} />
          <meshPhysicalMaterial
            ref={bodyMat}
            color="#6ee7ff"
            emissive="#6ee7ff"
            emissiveIntensity={1.2}
            roughness={0.06}
            metalness={0.88}
            clearcoat={1}
            clearcoatRoughness={0.08}
            transmission={0.22}
            thickness={0.45}
            ior={1.45}
          />
        </mesh>
      </Float>
    </group>
  );
}

function FlyingProjection({ live }: { live: React.MutableRefObject<LiveDynamics> }) {
  const shell = useRef<THREE.Group>(null);

  useFrame(({ clock }) => {
    if (!shell.current) return;
    const t = clock.elapsedTime;
    const { order, projX, projY, theta1, theta2 } = live.current;
    const orbit = R + 2.4;
    const fly = 0.65 + Math.sin(t * 0.9) * 0.4;
    shell.current.position.set(
      projX * orbit + Math.sin(t * 0.65 + theta1) * fly,
      Math.sin(t * 0.5) * 1.1 + order * 0.85 + 0.35,
      projY * orbit + Math.cos(t * 0.48 + theta2) * fly
    );
    shell.current.rotation.set(t * 0.55, t * 0.42, t * 0.28);
  });

  return (
    <group ref={shell}>
      <Float speed={2.2} floatIntensity={0.75} rotationIntensity={0.35}>
        <mesh>
          <icosahedronGeometry args={[0.58 + 0.08, 1]} />
          <meshPhysicalMaterial
            color="#6ee7ff"
            emissive="#6ee7ff"
            emissiveIntensity={3.2}
            wireframe
            transparent
            opacity={0.92}
            toneMapped={false}
          />
        </mesh>
      </Float>
    </group>
  );
}

function OscillatorField({ telemetry }: { telemetry: Telemetry | null }) {
  const group = useRef<THREE.Group>(null);
  const ring = useRef<THREE.Mesh>(null);
  const live = useLiveDynamics(telemetry);

  useFrame(({ clock }, delta) => {
    const { kappa, order } = live.current;
    if (group.current) group.current.rotation.y += delta * (0.05 + kappa * 0.08);
    if (ring.current) {
      ring.current.rotation.z += delta * 0.42;
      ring.current.rotation.x = Math.PI / 2 + Math.sin(clock.elapsedTime * 0.38) * 0.35;
      const s = R + 0.55 + order * 1.8 + Math.sin(clock.elapsedTime * 1.5) * 0.12;
      ring.current.scale.setScalar(s / (R + 0.55));
      (ring.current.material as THREE.MeshBasicMaterial).opacity = 0.22 + order * 0.55;
    }
  });

  return (
    <group ref={group}>
      <CouplingWeb live={live} />
      {Array.from({ length: N_OSCILLATORS }, (_, i) => (
        <OscillatorNode key={i} index={i} live={live} />
      ))}
      <mesh ref={ring} rotation={[Math.PI / 2, 0, 0]}>
        <torusGeometry args={[R + 0.55, 0.028, 10, 160]} />
        <meshBasicMaterial color="#c084fc" transparent opacity={0.35} toneMapped={false} />
      </mesh>
      <FlyingProjection live={live} />
    </group>
  );
}

const NEBULA_VERT = `
varying vec3 vDir;
void main() {
  vDir = normalize(position);
  gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
}
`;

const NEBULA_FRAG = `
precision highp float;
varying vec3 vDir;
uniform float uTime;

float hash(vec3 p){ p = fract(p * 0.3183099 + 0.1); p *= 17.0; return fract(p.x * p.y * p.z * (p.x + p.y + p.z)); }
float noise(vec3 x){
  vec3 i = floor(x); vec3 f = fract(x); f = f * f * (3.0 - 2.0 * f);
  return mix(mix(mix(hash(i+vec3(0,0,0)),hash(i+vec3(1,0,0)),f.x),
                 mix(hash(i+vec3(0,1,0)),hash(i+vec3(1,1,0)),f.x),f.y),
             mix(mix(hash(i+vec3(0,0,1)),hash(i+vec3(1,0,1)),f.x),
                 mix(hash(i+vec3(0,1,1)),hash(i+vec3(1,1,1)),f.x),f.y),f.z);
}
float fbm(vec3 p){ float v=0.0,a=0.5; for(int i=0;i<5;i++){ v+=a*noise(p); p*=2.02; a*=0.5; } return v; }

void main(){
  vec3 d = normalize(vDir);
  float t = uTime * 0.015;
  vec3 p = d * 2.2 + vec3(t, t * 0.5, -t * 0.3);
  float n = fbm(p);
  float clouds = smoothstep(0.42, 0.95, n);

  vec3 deep    = vec3(0.012, 0.012, 0.045);
  vec3 purple  = vec3(0.18, 0.07, 0.34);
  vec3 cyan    = vec3(0.10, 0.45, 0.62);
  vec3 magenta = vec3(0.46, 0.12, 0.42);

  vec3 col = deep;
  col = mix(col, purple, clouds * 0.85);
  float hi = smoothstep(0.6, 1.0, fbm(p * 1.7 + 5.0));
  col = mix(col, cyan, hi * 0.5 * clouds);
  col = mix(col, magenta, smoothstep(0.72, 1.0, n) * 0.4);

  // faint galactic band across the horizon
  float band = exp(-pow(d.y * 2.4, 2.0)) * 0.14;
  col += vec3(0.20, 0.26, 0.42) * band;

  gl_FragColor = vec4(col, 1.0);
}
`;

function Nebula() {
  const matRef = useRef<THREE.ShaderMaterial>(null);
  const uniforms = useMemo(() => ({ uTime: { value: 0 } }), []);
  useFrame(({ clock }) => {
    if (matRef.current) matRef.current.uniforms.uTime.value = clock.elapsedTime;
  });
  return (
    <mesh renderOrder={-10}>
      <sphereGeometry args={[90, 48, 48]} />
      <shaderMaterial
        ref={matRef}
        vertexShader={NEBULA_VERT}
        fragmentShader={NEBULA_FRAG}
        uniforms={uniforms}
        side={THREE.BackSide}
        depthWrite={false}
        fog={false}
      />
    </mesh>
  );
}

function Effects() {
  return (
    <EffectComposer multisampling={0}>
      <Bloom
        intensity={1.35}
        luminanceThreshold={0.28}
        luminanceSmoothing={0.78}
        mipmapBlur
      />
      <ChromaticAberration
        blendFunction={BlendFunction.NORMAL}
        offset={new THREE.Vector2(0.0008, 0.0008)}
        radialModulation={false}
        modulationOffset={0}
      />
      <Vignette eskil offset={0.12} darkness={1.1} />
    </EffectComposer>
  );
}

export function ShadowCanvas({
  telemetry,
  agentInvokes = [],
  dreamPreview = null,
}: {
  telemetry: Telemetry | null;
  agentInvokes?: import("../lib/types").AgentInvoke[];
  dreamPreview?: import("../lib/types").DreamPreview | null;
}) {
  return (
    <Canvas
      camera={{ position: [0, 7, 12], fov: 45 }}
      dpr={[1, 2]}
      gl={{
        antialias: true,
        alpha: false,
        powerPreference: "high-performance",
      }}
    >
      <color attach="background" args={["#020208"]} />
      <fog attach="fog" args={["#04030f", 16, 46]} />
      <ambientLight intensity={0.12} />
      <pointLight position={[8, 10, 6]} intensity={2.5} color="#6ee7ff" />
      <pointLight position={[-6, 5, -4]} intensity={1.8} color="#c084fc" />
      <pointLight position={[0, -2, 8]} intensity={0.6} color="#f472b6" />
      <Nebula />
      {/* Layered cosmos: distant drift + closer twinkling field */}
      <Stars radius={120} depth={60} count={6000} factor={4} fade speed={0.6} />
      <Stars radius={60} depth={28} count={2600} factor={3} fade speed={1.4} />
      <Sparkles
        count={200}
        scale={[16, 9, 16]}
        size={2}
        speed={0.35}
        opacity={0.35}
        color="#6ee7ff"
      />
      {/* cosmic dust */}
      <Sparkles
        count={140}
        scale={[22, 13, 22]}
        size={3.4}
        speed={0.18}
        opacity={0.22}
        color="#c084fc"
      />
      <Sparkles
        count={90}
        scale={[26, 16, 26]}
        size={4}
        speed={0.12}
        opacity={0.16}
        color="#f472b6"
      />
      <OscillatorField telemetry={telemetry} />
      <AgentBeams invokes={agentInvokes} />
      <DreamTrajectories preview={dreamPreview} />
      <Effects />
      <OrbitControls
        enablePan={false}
        maxDistance={22}
        minDistance={6}
        autoRotate
        autoRotateSpeed={0.35}
      />
    </Canvas>
  );
}
