# Percola — Network-Resilience Oracle 🕸️

**Percola sells the tipping point.** Given a trust/dependency graph it computes the
**critical attack fraction `f_c`** at which the giant connected component collapses —
a second-order connectivity phase transition — plus the collapse curve, the
susceptibility (second-cluster) peak that witnesses it, a `0..1` robustness scalar,
and the ranked **keystone set**. The same physics that decides whether a forest fire
jumps a firebreak or an outbreak becomes a pandemic.

Built on **`oracle-core`** (AIMarket Protocol v2). Where [Lumen](../lumen) ranks
*who* is reputable, Percola measures *when the whole network falls apart* — a global
property no per-node score can express.

```bash
# Threshold: two cliques joined by a bridge → tiny targeted f_c
curl -s -X POST http://localhost:9306/ai-market/v2/invoke -H "Content-Type: application/json" \
  -d '{"capability_id":"percola.threshold@v1","input":{"edges":[[0,1],[0,2],[1,2],[3,4],[3,5],[4,5],[2,6],[6,3]],"samples":7}}'
```

| Capability | What | Price |
|---|---|---|
| `percola.threshold@v1` | `f_c`, collapse curve, robustness, keystones (targeted + random attack) | $0.01 |
| `percola.verify@v1` | trustless replay — recompute the sweep and check the claimed `f_c` | $0.001 |

**Verifiable, not asserted.** The analysis is a pure function of a SHA-256
`graph_commitment`; the targeted removal order is deterministic (greedy max-degree,
lowest-index tie-break) and the random baseline seed is committed as
`H(commitment ‖ nonce)`. Any verifier replays the union–find over the exact order and
reproduces `P_inf(f)` and `f_c` bit-for-bit.

Full math, diagrams and use cases: [docs/en.md](docs/en.md) · [docs/ru.md](docs/ru.md) · [docs/es.md](docs/es.md).

Part of the [AICOM oracle family](https://github.com/alexar76/oracles). MIT.
