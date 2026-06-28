import { ORACLES, ORACLES_REPO, GITHUB_ORG, oracleGithubUrl } from "./oracles";
import { ScenePreview } from "./ScenePreview";

const FLOW = [
  { n: "01", h: "Discover", p: "An agent searches the AIMarket hub by intent (\"verifiable randomness\") and finds the oracle + price." },
  { n: "02", h: "Invoke", p: "It calls the capability through a micropayment channel — pay-per-call, no subscription." },
  { n: "03", h: "Verify", p: "Every result is Ed25519-signed with a proof; the agent verifies it without trusting the oracle." },
  { n: "04", h: "Settle", p: "A signed receipt debits the channel. Real metrics (latency, success) are measured, not faked." },
];

export function Home() {
  return (
    <div className="home" data-testid="home">
      <div className="home-inner">
        <header className="hero">
          <div className="kicker">AIMarket Protocol · v2</div>
          <h1>The Oracle Family</h1>
          <p>
            Seventeen live mathematical oracles for the autonomous AI economy. Each is a beautiful
            substrate that emits a <b>signed, verifiable artifact</b> agents genuinely need —
            randomness, time, consensus, reputation, routing, resilience, thermodynamics — discoverable and
            priced on one shared protocol. No mocks: only real, tested mathematics.
          </p>
          <div className="stats">
            <div className="stat"><b>17</b><span>oracles</span></div>
            <div className="stat"><b>370+</b><span>tests green</span></div>
            <div className="stat"><b>Ed25519</b><span>+ ML-DSA hybrid</span></div>
            <div className="stat"><b>3D</b><span>cosmic visuals</span></div>
          </div>
        </header>

        <section className="economy">
          <h2>How the economy works</h2>
          <p>
            Oracles don't sell hype — they sell <b>capabilities with provable value</b>. An agent
            discovers what it needs, invokes it, verifies the cryptographic proof, and pays per call.
            That's the whole loop, and every oracle below speaks it natively.
          </p>
          <div className="flow">
            {FLOW.map((s) => (
              <div className="step" key={s.n}>
                <div className="n">{s.n}</div>
                <h4>{s.h}</h4>
                <p>{s.p}</p>
              </div>
            ))}
          </div>
        </section>

        <h2 className="grid-title">The seventeen oracles</h2>
        <div className="cards">
          {ORACLES.map((o) => (
            <a
              className="card"
              key={o.slug}
              href={`?o=${o.slug}`}
              data-testid={`oracle-card-${o.slug}`}
              style={{ boxShadow: `0 0 0 1px transparent` }}
              onMouseEnter={(e) => (e.currentTarget.style.boxShadow = `0 14px 50px -20px ${o.accent}88, 0 0 0 1px ${o.accent}55`)}
              onMouseLeave={(e) => (e.currentTarget.style.boxShadow = `0 0 0 1px transparent`)}
            >
              <span className="testbadge">{o.tests} tests</span>
              <ScenePreview oracle={o} />
              <div className="body">
                <div className="name" style={{ color: o.accent }}>{o.name}</div>
                <div className="skill">{o.skill}</div>
                <div className="blurb">{o.blurb}</div>
                <div className="mathline" style={{ borderColor: o.accent }}>{o.math}</div>
                <div className="caps">
                  {o.caps.map((c) => (
                    <span className="cap" key={c.id} title={c.what}>
                      {c.id} <b>{c.price}</b>
                    </span>
                  ))}
                </div>
                <div className="enter" style={{ color: o.accent }}>Enter the live 3D oracle →</div>
                <div className="card-links">
                  {o.cockpitUrl && (
                    <a className="card-link cockpit" href={o.cockpitUrl} onClick={(e) => e.stopPropagation()}>
                      UMBRAL cave · oracle #1 experience →
                    </a>
                  )}
                  <a className="card-link github" href={oracleGithubUrl(o)} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()}>
                    ★ Source on GitHub →
                  </a>
                  {o.docsUrl && (
                    <a className="card-link docs" href={o.docsUrl} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()}>
                      Portal vs cave (docs)
                    </a>
                  )}
                </div>
              </div>
            </a>
          ))}
        </div>

        <footer className="home-footer">
          <span>AIMarket Protocol v2</span>
          <span>hub · <a href="https://modelmarket.dev" target="_blank" rel="noreferrer">modelmarket.dev</a></span>
          <span>Ed25519 + ML-DSA-65 (FIPS 204) hybrid signing</span>
          <span>MIT</span>
          <a href={ORACLES_REPO} target="_blank" rel="noreferrer">★ Oracle family on GitHub</a>
          <a href={GITHUB_ORG} target="_blank" rel="noreferrer">whole ecosystem · github.com/alexar76</a>
        </footer>
      </div>
    </div>
  );
}
