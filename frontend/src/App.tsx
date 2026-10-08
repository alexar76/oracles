import { Component, lazy, ReactNode, Suspense } from "react";
import { CosmicCanvas } from "./CosmicCanvas";
import { Home } from "./Home";
import { ORACLES, oracleBySlug } from "./oracles";
import { LOADERS } from "./sceneLoaders";

class ErrorBoundary extends Component<{ children: ReactNode }, { err: string | null }> {
  state = { err: null as string | null };
  static getDerivedStateFromError(e: any) { return { err: String(e?.message || e) }; }
  render() {
    if (this.state.err) return <div className="err">scene error: {this.state.err}</div>;
    return this.props.children;
  }
}

export function App() {
  const params = new URLSearchParams(location.search);
  const o = params.get("o");
  // Embed mode: render ONLY the scene/canvas — no overlay, picker, or nav chrome.
  // Used by alien-monitor's NodeDetail to show a compact live preview in an iframe.
  const embed = params.get("embed") === "1";

  // landing page when no oracle is selected
  if (!o || (!LOADERS[o] && !oracleBySlug(o)?.ambient)) {
    return <Home />;
  }

  const meta = oracleBySlug(o)!;

  if (meta.ambient) {
    return (
      <>
        {!embed && (
          <>
            <div className="picker">
              {ORACLES.map((x) => (
                <a key={x.slug} className={x.slug === o ? "active" : ""} href={`?o=${x.slug}`}>{x.slug}</a>
              ))}
            </div>
            <a className="scene-back" href="./">← Family</a>
          </>
        )}
        <iframe
          className="ambient-frame"
          src={`/ambient/${meta.slug}/index.html`}
          title={`${meta.name} ambient visual`}
        />
      </>
    );
  }

  const Scene = lazy(LOADERS[o]);
  return (
    <>
      {!embed && (
        <>
          <div className="overlay"><h1 style={{ color: meta.accent }}>{meta.name.toUpperCase()}</h1><p>{meta.skill}</p></div>
          <div className="picker">
            {ORACLES.map((x) => (
              <a key={x.slug} className={x.slug === o ? "active" : ""} href={`?o=${x.slug}`}>{x.slug}</a>
            ))}
          </div>
          <a className="scene-back" href="./">← Family</a>
          {meta.cockpitUrl && (
            <a className="scene-cockpit" href={meta.cockpitUrl}>
              Open Platon UMBRAL cave (live oracle #1) →
            </a>
          )}
        </>
      )}
      <ErrorBoundary>
        <Suspense fallback={null}>
          <CosmicCanvas camera={meta.camera}>
            <Scene />
          </CosmicCanvas>
        </Suspense>
      </ErrorBoundary>
    </>
  );
}
