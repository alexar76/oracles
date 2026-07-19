# Ablation — Systemic Cascade-Risk Oracle 🏔️

**Ablation sells the tail.** Given an exposure / dependency graph it treats the network as a
**Bak–Tang–Wiesenfeld abelian sandpile** (self-organized criticality), drives unit stress
into it, and measures the **heavy-tailed distribution of cascade magnitudes**: the fitted
power-law exponent `tau` (MLE) with a KS goodness-of-fit, the mean and **tail (VaR/CVaR at
95% & 99%)** avalanche size, and the **trigger nodes** that most often ignite large
cascades. The same physics as a sandpile at the angle of repose, an earthquake fault, or a
power-grid blackout.

Built on **`oracle-core`** (AIMarket Protocol v2). Where [Percola](../percola) gives a
*static* connectivity threshold `f_c`, Ablation gives the *dynamic* answer — the **size
distribution of the cascades** a driven, dissipative network produces under load. Small
`tau` / heavy tail = one default ripples across the whole market.

```bash
# Cascade: a small exposure ring with a hub → heavy tail
curl -s -X POST http://localhost:9308/ai-market/v2/invoke -H "Content-Type: application/json" \
  -d '{"capability_id":"ablation.cascade@v1","input":{
        "edges":[["a","b"],["b","c"],["c","a"],["a","h"],["h","d"],["d","e"],["e","h"]],
        "grains":3000,"nonce":"demo"}}' | jq '{tau,ks,mean_avalanche,cvar99,triggers}'
```

| Capability | What | Price |
|---|---|---|
| `ablation.cascade@v1` | avalanche-size distribution, power-law `tau` + KS, mean & tail VaR/CVaR (95% & 99%), trigger nodes | $0.01 |
| `ablation.verify@v1` | trustless replay — re-run the sandpile, recompute the order-independent topple total and `tau`, check the claim | $0.001 |

**Verifiable, not asserted.** The analysis is a pure function of a SHA-256
`config_commitment`; the drive-schedule seed is committed as `H(commitment ‖ nonce)`. The
**abelian property** (Dhar's theorem) guarantees the per-site topple counts are
**independent of relaxation order**, so any verifier replays the driven-dissipative sandpile
and reproduces the topple total and `tau` **bit-for-bit**. The test suite asserts this
directly — three different relaxation orders give identical topple counts and final state.

Full math, diagrams and use cases: [docs/en.md](docs/en.md) · [docs/ru.md](docs/ru.md) · [docs/es.md](docs/es.md).

Part of the [AICOM oracle family](https://github.com/alexar76/oracles). MIT.
