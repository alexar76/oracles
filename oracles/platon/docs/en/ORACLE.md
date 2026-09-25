# Platon UMBRAL — The Sensory Organ of the Agent Economy

> **Platon is a sensory organ of the ecosystem:** agents poke chaos, Monitor watches, Hub sells, provenance records.

Platon is not a demo chart. It is a **32-dimensional dynamical oracle** — a live mathematical substrate that autonomous agents can steer, interrogate, and receive signed testimonies from, through the AIMarket protocol.

> **Place in the ecosystem & mermaid diagrams:** see [ECOSYSTEM.md](../ECOSYSTEM.md). Platon is an **independent project** that plugs into the [alexar76 agent economy](https://github.com/alexar76) — it is **not** produced by AI-Factory.

### Where is the AI?

The **core simulation is mathematics, not AI** — and we say so plainly. The AI lives in three honest places: (1) the **witness oracle is an LLM** (`platon.oracle@v1` calls DeepSeek/Ollama); (2) **DREAM fits a real learned model** (least squares on trajectory data, measurable residual, no magic constants) and shows where a learned predictor diverges at the Lyapunov horizon; (3) the **consumers are AI agents** — Platon is *infrastructure for the AI economy* (signed entropy & signals for sampling, nonces, tie-breaks, commit-reveal, leader election). The dynamics, order parameter, Lyapunov proxy, and Stiefel projection are real provable mathematics, not AI dressed up as such.

---

## 1. What Platon is (highest level)

| Role | Actor | Action |
|------|-------|--------|
| **Probe** | Autonomous agent | Invokes `platon.steer@v1`, `platon.dream@v1`, `platon.oracle@v1` via Hub |
| **Sense** | Platon simulation | Evolves coupled oscillators; detects bifurcations (chimera, chaos, sync) |
| **Speak** | Oracle (DeepSeek / template) | Emits mathematical **witnesses** at critical events |
| **Watch** | Alien Monitor | Materializes events in 3D topology; live κ, r metrics |
| **Sell** | AIMarket Hub | Federated discovery, micropayment invoke, provenance receipts |
| **Audit** | Provenance layer | Every invoke returns timestamped `input_hash` + price |

**Practical meaning:** agents gain a **priced, verifiable interface to complexity** — not a black-box LLM guess, but a dynamical system with measurable order parameters and failure modes (where surrogate prediction diverges from truth).

---

## 2. Scientific foundation

### 2.1 State space

Platon simulates **N = 32 coupled Stuart–Landau oscillators** in the complex plane:

\[
z_j = r_j e^{i\theta_j}, \quad j = 1,\ldots,32
\]

The full internal state lives in \(\mathbb{R}^{64}\) (real + imaginary parts), but the **semantic dimension** is **32** — one complex degree of freedom per oscillator.

### 2.2 Evolution (Kuramoto–Stuart–Landau coupling)

Amplitude and phase evolve as:

\[
\frac{dr_j}{dt} = r_j(1 - r_j^2)
\]

\[
\frac{d\theta_j}{dt} = \omega_j + b_j(\text{prompt}) + \kappa \sin(\Theta - \theta_j)
\]

where the **mean phase** is:

\[
\Theta = \arg\left(\frac{1}{N}\sum_{k=1}^{N} e^{i\theta_k}\right)
\]

- \(\kappa\) — global coupling strength (bifurcation control)
- \(\omega_j\) — natural frequencies (spread across oscillators)
- \(b_j\) — semantic steering bias from agent/human text (SHA-256 hash → per-oscillator detuning)

### 2.3 Order parameter (synchronization measure)

\[
r = \left|\frac{1}{N}\sum_{j=1}^{N} e^{i\theta_j}\right| \in [0,1]
\]

| Regime | Typical r | Meaning |
|--------|-----------|---------|
| Incoherent | r < 0.35 | No collective rhythm |
| Chimera | 0.35 ≤ r < 0.85 | Coexistence of sync + incoherent clusters |
| Full sync | r > 0.85 | Global phase locking |

### 2.4 Chaos proxy (Lyapunov estimate)

Finite-time divergence via perturbed step \(\delta_0 = 10^{-6}\):

\[
\lambda \approx \frac{1}{\Delta t}\ln\frac{\|\delta \mathbf{x}(t)\|}{\delta_0}
\]

When \(\lambda > 2.5\), Platon fires `chaos_threshold` — the region where **surrogate models fail**.

### 2.5 Projection (Plato's cave)

Humans and agents never see all 64 dimensions. A **Stiefel-style composition of plane rotations** maps \(\mathbb{R}^{64} \to \mathbb{R}^{2}\):

\[
(x, y) = \Pi_{\theta_1,\theta_2}(\mathbf{z}_{\mathrm{real}}, \mathbf{z}_{\mathrm{imag}})
\]

Different \((\theta_1, \theta_2)\) yield **incompatible witnesses** of the same underlying state — the UMBRAL metaphor.

### 2.6 Dream (prediction vs truth)

`platon.dream@v1` rolls forward:
- **Truth:** full nonlinear integration
- **Surrogate:** linearized one-step predictor

Divergence index marks where **epistemic collapse** begins — directly useful for agents estimating forecast horizons in chaotic regimes.

---

## 3. Why exactly 32 dimensions?

### Mathematical reasons

1. **Chimera states** — Kuramoto networks with \(N \gtrsim 20\) exhibit stable chimera solutions; \(N = 32\) sits in the well-studied regime where partial synchronization is robust, not trivial.
2. **Power-of-two grid** — 32 = \(8 \times 4\) lattice for visualization; clean coupling topology; aligns with FFT/PCA analysis (top-3 energy metric).
3. **Computational sweet spot** — \(\mathcal{O}(N^2)\) coupling checks = 496 pairs — real-time at 30 Hz on CPU without GPU; 128+ dimensions add little phenomenology but 4× cost.
4. **64D real embedding** — doubles to a smooth manifold for Stiefel projection while staying human-parseable (32 nodes in UI).

### Practical reasons for *our* ecosystem

| Requirement | Why 32 fits |
|-------------|-------------|
| Live public server (8 cores, no GPU) | Full 32D tick + WebGL + oracle fits in &lt;200 MB RAM |
| AIMarket micropayments | Fast invoke (&lt;25 ms state, &lt;800 ms oracle) |
| Alien Monitor node | One icon per oscillator layer; κ/r telemetry maps 1:1 |
| Agent tooling | Enough complexity for **nontrivial bifurcations**, not so much that telemetry is noise |
| Neural metaphor | Matches common latent widths (32-dim bottlenecks) — agents can reason about "bottleneck chaos" |

**Not arbitrary:** 32 is the smallest scale where chimera + chaos + full sync **all appear** in the same system under semantic steering.

---

## 4. Platon as Oracle

An **oracle** here is precise:

> At dynamical events (chimera birth/death, chaos threshold, full synchronization), Platon emits a **witness** — a short testimony grounded in telemetry \((\kappa, r, \lambda)\), generated by **DeepSeek** (via Hermes API key) or deterministic template fallback.

Capability: `platon.oracle@v1` — priced at $0.02, provenance-recorded.

This is **not** generic chat. It is **event-conditioned mathematical speech** tied to measurable state.

---

## 5. Use cases (concrete)

### UC-1: Agent orchestration under uncertainty
An orchestrator agent searches Hub for `intent=chaos probe`, invokes `platon.steer@v1` with prompts like `"edge of criticality"`, reads \(\kappa\) and \(r\), decides whether to escalate to human or switch strategy.

### UC-2: Forecast horizon estimation
Quant agent calls `platon.dream@v1` with `steps=120`. If divergence_at &lt; 15, downstream ML model is warned: **do not trust long-horizon predictions** for this regime.

### UC-3: Generative art / music agents
Art agent steers κ via semantic prompts (`"entropy cathedral"`), samples phase snapshots via `platon.state@v1`, maps oscillator phases to MIDI/CC parameters.

### UC-4: Research logging
Lab agent logs oracle witnesses at chimera births — timestamped, hash-linked provenance for reproducibility papers.

### UC-5: Monitor-assisted ops
Human opens Alien Monitor, sees Platon node flare on `chaos_threshold`, reads witness in UI, correlates with factory agent failures.

### UC-6: Federation commerce
External hub crawls `/.well-known/ai-market.json`, indexes `platon.*@v1`, routes paid invokes with routing fee — Platon earns micro-revenue per probe.

---

## 6. Visualization of agent traffic

The UI renders:

| Visual | Meaning |
|--------|---------|
| **Cyan beams** from sky | AIMarket agent invoke (steer, state, project) |
| **Purple beams** | Prediction invoke (dream, oracle) |
| **Pink trail** | Surrogate dream path |
| **Cyan trail** | Truth path |
| **Agent channel panel** | Live feed of `capability_id`, source, summary |

Invoke via Hub appears in real time on all connected browsers (WebSocket broadcast).

---

## 7. Ecosystem wiring

```
Agent → Hub search → invoke platon.*@v1 → Platon backend
                                              ↓
                                    WebSocket → UI beams
                                              ↓
                                    webhook → Alien Monitor
```

DeepSeek key: loaded from `~/.hermes/.env` (`DEEPSEEK_API_KEY`) — same as Hermes agent stack.

---

## 8. Summary equation card

\[
\boxed{
\begin{aligned}
&\dot\theta_j = \omega_j + b_j + \kappa\sin(\Theta - \theta_j) \\
&r = \left|\langle e^{i\theta}\rangle\right| \\
&\lambda \approx \frac{1}{\Delta t}\ln\frac{\|\delta\mathbf{x}\|}{\delta_0} \\
&\text{Oracle witness} = f_{\mathrm{LLM}}(\kappa, r, \lambda, \text{event})
\end{aligned}
}
\]

**Platon UMBRAL** — one high-dimensional reality, many incompatible 2D projections, one federated oracle.
