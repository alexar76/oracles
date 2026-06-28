import { FormEvent, useState } from "react";
import { SafeShadowCanvas } from "./components/SafeShadowCanvas";
import { AskPanel } from "./components/AskPanel";
import { usePlatonSocket } from "./hooks/usePlatonSocket";
import { formatMetric } from "./lib/types";
import { LANGS, detectLang, dict } from "./lib/i18n";

export default function App() {
  const {
    telemetry,
    connected,
    witnesses,
    agentInvokes,
    dreamPreview,
    steer,
    project,
    dream,
    dreaming,
  } = usePlatonSocket();
  const [lang, setLang] = useState(detectLang());
  const t = dict[lang];
  const [prompt, setPrompt] = useState("entropy cathedral");

  function onSteer(e: FormEvent) {
    e.preventDefault();
    if (prompt.trim()) steer(prompt.trim());
  }

  return (
    <div className="app" data-testid="platon-app">
      <header className="header">
        <div>
          <div className="logo">
            Platon <span>UMBRAL</span>
            <span className="oracle-badge">ORACLE</span>
          </div>
          <div className="tagline">{t.tagline}</div>
        </div>
        <div className="header-actions">
          <div className="lang-switch" data-testid="lang-switch" role="group" aria-label="Language">
            {LANGS.map((l) => (
              <button
                key={l}
                type="button"
                className={l === lang ? "active" : ""}
                aria-pressed={l === lang}
                onClick={() => setLang(l)}
              >
                {l.toUpperCase()}
              </button>
            ))}
          </div>
          <button
            type="button"
            data-testid="dream-btn"
            className={dreaming ? "active" : ""}
            onClick={() => dream(60)}
          >
            {dreaming ? t.dreaming : t.dream}
          </button>
        </div>
      </header>

      <main className="main">
        <div className="canvas-wrap" data-testid="shadow-canvas">
          <SafeShadowCanvas
            telemetry={telemetry}
            agentInvokes={agentInvokes}
            dreamPreview={dreamPreview}
          />
          <div className="projection-hint">{t.projectionHint}</div>
        </div>

        <aside className="sidebar">
          <div className="panel">
            <h3>{t.telemetry}</h3>
            <div className="metrics" data-testid="metrics-panel">
              <div className="metric">
                <label>{t.kappa}</label>
                <span className="val" data-testid="metric-kappa">
                  {telemetry ? formatMetric(telemetry.kappa) : "—"}
                </span>
              </div>
              <div className="metric">
                <label>{t.order}</label>
                <span className="val" data-testid="metric-order">
                  {telemetry ? formatMetric(telemetry.order_parameter) : "—"}
                </span>
              </div>
              <div className="metric">
                <label>{t.lyapunov}</label>
                <span className="val" data-testid="metric-lyapunov">
                  {telemetry ? formatMetric(telemetry.lyapunov) : "—"}
                </span>
              </div>
              <div className="metric">
                <label>{t.pca}</label>
                <span className="val">
                  {telemetry ? formatMetric(telemetry.pca_energy_3) : "—"}
                </span>
              </div>
            </div>
          </div>

          <div className="panel agent-panel" data-testid="agent-feed">
            <h3>{t.agentPanel}</h3>
            {agentInvokes.length === 0 && (
              <p className="muted-line">
                {t.agentWaiting} <code>platon.*@v1</code>…
              </p>
            )}
            {agentInvokes.map((inv, i) => (
              <div
                key={`${inv.timestamp}-${i}`}
                className={`agent-invoke${inv.is_prediction ? " prediction" : ""}`}
              >
                <div className="agent-meta">
                  <span className="cap">{inv.capability_id}</span>
                  <span className="src">{inv.source}</span>
                </div>
                <div className="agent-summary">{inv.summary}</div>
              </div>
            ))}
          </div>

          <AskPanel lang={lang} t={t} />

          <div className="panel">
            <h3>{t.steerTitle}</h3>
            <form className="steer-form" onSubmit={onSteer}>
              <input
                data-testid="steer-input"
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                placeholder={t.steerPlaceholder}
                aria-label="Steering prompt"
              />
              <button type="submit" data-testid="steer-btn">
                {t.steerBtn}
              </button>
            </form>
          </div>

          <div className="panel">
            <h3>{t.projectionTitle}</h3>
            <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
              <button type="button" onClick={() => project(0.3, 0.8)}>
                θ₁=0.3
              </button>
              <button type="button" onClick={() => project(1.1, 2.0)}>
                θ₂=2.0
              </button>
              <button type="button" onClick={() => project(2.4, 0.5)}>
                {t.flip}
              </button>
            </div>
          </div>

          <div className="witnesses" data-testid="witness-feed">
            <h3 style={{ marginBottom: "0.75rem", fontSize: "0.65rem", color: "var(--muted)", letterSpacing: "0.15em" }}>
              {t.witnesses}
            </h3>
            {witnesses.length === 0 && (
              <p style={{ color: "var(--muted)", fontSize: "0.75rem" }}>
                {t.witnessWaiting}
              </p>
            )}
            {witnesses.map((w, i) => (
              <div key={`${w.timestamp}-${i}`} className="witness">
                <div className="event">
                  {w.event.replace(/_/g, " ")}
                  {w.source && (
                    <span className="witness-src"> · {w.source}{w.model ? `/${w.model}` : ""}</span>
                  )}
                </div>
                <div className="text">{w.text}</div>
              </div>
            ))}
          </div>
        </aside>
      </main>

      <footer className="footer">
        <span>
          <span className={`status-dot${connected ? "" : " offline"}`} />
          {connected ? t.live : t.connecting} · tick {telemetry?.tick ?? 0} ·{" "}
          {telemetry?.viewers ?? 0} {t.projections} · {agentInvokes.length} {t.agentCalls}
        </span>
        <span>{t.footerRight}</span>
      </footer>
    </div>
  );
}
