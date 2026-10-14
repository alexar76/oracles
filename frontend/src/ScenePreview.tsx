import { lazy, Suspense, useEffect, useRef, useState } from "react";
import type { ComponentType, LazyExoticComponent } from "react";
import { Canvas } from "@react-three/fiber";
import { OrbitControls, Stars } from "@react-three/drei";
import { Bloom, EffectComposer } from "@react-three/postprocessing";
import { LOADERS } from "./sceneLoaders";
import type { Oracle } from "./oracles";

// Lazy scene components are cached so scrolling a card in and out of view does
// not re-create the module each time.
const sceneCache: Record<string, LazyExoticComponent<ComponentType>> = {};
function getScene(slug: string): LazyExoticComponent<ComponentType> | null {
  if (!LOADERS[slug]) return null;
  if (!sceneCache[slug]) sceneCache[slug] = lazy(LOADERS[slug]);
  return sceneCache[slug];
}

// The "virtual screen" (16:9) an ambient HTML scene renders at before being
// scaled to the card. Matches the full-screen viewport so its HUD text keeps
// the same (good) proportions it has in the full scene, just smaller.
const AMBIENT_SRC_W = 1440;
const AMBIENT_SRC_H = 810;

/**
 * Live 3D preview for a landing card. VIEWPORT-GATED: the WebGL canvas (R3F
 * oracles) or the cosmic ambient iframe (percola/fermat/ablation/landauer) only
 * mounts while the card is near the viewport and UNMOUNTS when it scrolls away —
 * so across all 17 cards we never exceed the browser's ~16 live WebGL contexts.
 * Off-screen, a cheap accent-tinted cosmic poster holds the slot. Replaces the
 * old pre-recorded .webm previews with the real, animated scene.
 */
export function ScenePreview({ oracle }: { oracle: Oracle }) {
  const ref = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(false);
  const [boxW, setBoxW] = useState(0);

  useEffect(() => {
    const el = ref.current;
    if (!el || typeof IntersectionObserver === "undefined") {
      setVisible(true);
      return;
    }
    const io = new IntersectionObserver(
      ([entry]) => setVisible(entry.isIntersecting),
      { rootMargin: "260px 0px", threshold: 0.01 }
    );
    io.observe(el);
    return () => io.disconnect();
  }, []);

  // Measure the card's preview width so the ambient iframe can render at a
  // full-screen virtual size and be scaled down to fit (keeps HUD text small).
  useEffect(() => {
    const el = ref.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(([e]) => setBoxW(e.contentRect.width));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const poster = (
    <div
      className="poster"
      style={{
        background: `radial-gradient(115% 85% at 50% 16%, ${oracle.accent}33, transparent 60%), radial-gradient(90% 70% at 82% 104%, ${oracle.accent}22, transparent 70%), #04030f`,
      }}
    >
      <span style={{ color: oracle.accent }}>{oracle.name}</span>
    </div>
  );

  return (
    <div className="preview" ref={ref}>
      {!visible ? (
        poster
      ) : oracle.ambient ? (
        <iframe
          className="preview-frame"
          src={`/ambient/${oracle.slug}/index.html`}
          title={`${oracle.name} live preview`}
          loading="lazy"
          tabIndex={-1}
          aria-hidden="true"
          style={{
            width: AMBIENT_SRC_W,
            height: AMBIENT_SRC_H,
            transform: `scale(${(boxW || 340) / AMBIENT_SRC_W})`,
            transformOrigin: "top left",
          }}
        />
      ) : (
        <PreviewCanvas oracle={oracle} />
      )}
    </div>
  );
}

function PreviewCanvas({ oracle }: { oracle: Oracle }) {
  const Scene = getScene(oracle.slug);
  if (!Scene) return null;
  return (
    <Canvas
      className="preview-canvas"
      camera={{ position: oracle.camera, fov: 48 }}
      dpr={[1, 1.5]}
      gl={{ antialias: true, alpha: false, powerPreference: "low-power" }}
      frameloop="always"
    >
      <color attach="background" args={["#04030f"]} />
      <fog attach="fog" args={["#04030f", 18, 55]} />
      <ambientLight intensity={0.18} />
      <pointLight position={[8, 10, 6]} intensity={2.2} color="#6ee7ff" />
      <pointLight position={[-6, 5, -4]} intensity={1.5} color="#c084fc" />
      <pointLight position={[0, -3, 8]} intensity={0.6} color="#f472b6" />
      <Stars radius={90} depth={45} count={900} factor={3} fade speed={0.5} />
      <Suspense fallback={null}>
        <Scene />
      </Suspense>
      <EffectComposer multisampling={0}>
        <Bloom intensity={0.95} luminanceThreshold={0.3} luminanceSmoothing={0.8} mipmapBlur />
      </EffectComposer>
      {/* autoRotate gives a turntable feel; pointer-events are disabled in CSS so
          clicks fall through to the card link (no user drag/zoom). */}
      <OrbitControls enablePan={false} enableZoom={false} autoRotate autoRotateSpeed={0.55} />
    </Canvas>
  );
}
