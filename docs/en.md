# Oracles — verifiable math for the agent economy (EN)

Seventeen live mathematical oracles on shared **`oracle-core`**. Each emits a **signed, verifiable artifact** agents discover and pay for on [AIMarket Protocol v2](https://github.com/alexar76/aimarket-protocol) via [modelmarket.dev](https://modelmarket.dev).

> **Landing:** [oracles.modelmarket.dev](https://oracles.modelmarket.dev) · **Ecosystem:** [modeldev.modelmarket.dev](https://modeldev.modelmarket.dev) · **Repo:** [alexar76/oracles](https://github.com/alexar76/oracles)

---

## How the economy works

1. **Discover** — an agent searches the hub by intent (`verifiable randomness`, `consensus`, …).
2. **Invoke** — micropayment channel, pay-per-call capability.
3. **Verify** — Ed25519 (+ hybrid ML-DSA) signed proof; no trust in the operator.
4. **Settle** — signed receipt debits the channel; real latency/success metrics in the manifest.

---

## The seventeen oracles

| Oracle | Skill | Capability examples |
|--------|-------|---------------------|
| **Platon** | Verifiable randomness + dynamical oracle | `platon.random@v1`, `platon.beacon@v1`, commit-reveal |
| **Chronos** | Verifiable delay (VDF) | `chronos.eval@v1`, `chronos.verify@v1` |
| **Lattice** | Quasi-random low-discrepancy sequences | `lattice.sequence@v1` |
| **Murmuration** | Robust consensus aggregation | `murmuration.aggregate@v1` |
| **Lumen** | Reputation / trust scores | `lumen.reputation@v1` |
| **Colony** | TSP optimization + quality certificate | `colony.optimize@v1` |
| **Turing** | Blue-noise structured sampling | `turing.bluenoise@v1` |
| **Percola** | Network-resilience / percolation threshold | `percola.threshold@v1`, `percola.verify@v1` |
| **Fermat** | Least-time routing + dual certificate | `fermat.route@v1`, `fermat.verify@v1` |
| **Ablation** | Systemic cascade-risk (SOC tail) | `ablation.cascade@v1`, `ablation.verify@v1` |
| **Landauer** | Thermodynamic compute-cost audit | `landauer.audit@v1`, `landauer.verify@v1` |
| **Sortes** | Ungrindable ECVRF verifiable randomness (offline-checkable) | `sortes.draw@v1`, `sortes.verify@v1` |
| **Gauss** | GP regression: calibrated posterior + best next point | `gauss.field@v1`, `gauss.suggest@v1`, `gauss.verify@v1` |
| **Aestus** | RSW time-lock puzzles (no trapdoor holder) | `aestus.seal@v1`, `aestus.open@v1`, `aestus.verify@v1` |
| **Betti** | Persistent homology + shape-drift alarm | `betti.homology@v1`, `betti.distance@v1` |
| **Kantor** | Exact optimal transport + dual certificate | `kantor.transport@v1`, `kantor.verify@v1` |
| **Fourier** | Graph-spectral analysis (Fiedler, spectral cut) | `fourier.spectrum@v1`, `fourier.verify@v1` |

**Chronos × Platon** — wrap Platon output in a VDF for an *unbiasable* beacon (operator cannot grind the result).

---

## In production: the Agent Lottery

The **[Agent Lottery](https://github.com/alexar76/lottery)** ([live](https://lottery.modelmarket.dev/)) is the canonical real consumer — an autonomous economic actor that composes **three oracles** into one unbiasable, on-chain-verifiable draw, paying per call through the Hub (`POST /ai-market/v2/invoke`, 1% routing fee) or the oracle-family directly:

| Oracle · capability | Used for | Price |
|---------------------|----------|-------|
| **Platon** `platon.random@v1` | draw entropy, committed at round close | $0.004 |
| **Chronos** `chronos.eval@v1` | Wesolowski VDF, verified on-chain (`onchainVdf`) | $0.01 |
| **Chronos** `chronos.verify@v1` | off-chain VDF proof check | $0.001 |
| **Lumen** `lumen.reputation@v1` | EigenTrust scores → signed reputation vouchers (+0…50% odds) | $0.005 |
| **Platon** `platon.ask@v1` | AI Treasurer LLM allocation of the prize / machine-UBI split (optional) | $0.003 |

`platon.random@v1` seeds `chronos.eval@v1`, so the winning ticket is fixed by enforced sequential time (the **Chronos × Platon** beacon above) — neither operator nor agent can grind it; **Lumen** then reputation-weights the draw. Every call is an Ed25519-signed receipt booked as the lottery's opex, and the Hub tithes its routing fees back as a **machine UBI** for agents.

---

## Platon UMBRAL cave (separate product)

All seventeen oracles are **full AIMarket products**. The family landing is the **portal** (economy loop + 3D showcase). **Platon UMBRAL** at `/platon/umbral` is a **separate cave product** that educationally presents oracle #1 with live backend and controls.

→ **[Seventeen oracles & Platon cave (EN)](platon-preview.en.md)** · [RU](platon-preview.ru.md)

---

## 3D cosmic visuals

Run the shared R3F portal locally:

```bash
cd frontend && npm install && npm run dev
# http://localhost:5180/  — cards with live video loops
# http://localhost:5180/?o=platon  — educational Platon preview (browser-only; not UMBRAL)
# UMBRAL cockpit (separate app): http://localhost:5174/umbral  or  /platon/umbral in prod
```

Recorded loops ship in `frontend/public/media/*.webm` (also embedded in the [GitHub README](https://github.com/alexar76/oracles#gallery)).

---

## Dev & tests

```bash
python3.11 -m venv .venv
.venv/bin/pip install -e "core[dev,pqc]"
for o in chronos lattice murmuration lumen colony turing percola fermat ablation landauer sortes gauss aestus betti kantor fourier; do .venv/bin/pip install -e "oracles/$o"; done
.venv/bin/pip install -e "oracles/platon/backend[dev]"
PLATON_TESTING=1 .venv/bin/python -m pytest core/tests oracles/*/tests oracles/platon/backend/tests -q
```

**280+ tests** green across the family.

---

## Related ecosystem docs

- [AIMarket Hub](https://github.com/alexar76/aimarket-hub) — lists and routes oracle capabilities
- [aimarket-agent](https://github.com/alexar76/aimarket-agent) — discover → invoke from Python
- [Protocol ecosystem map](https://github.com/alexar76/aimarket-protocol/blob/main/ecosystem.md)

**Other languages:** [ru.md](ru.md) · [es.md](es.md)
