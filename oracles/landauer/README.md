# Landauer — Thermodynamic Compute-Cost Oracle 🔥

**Landauer sells the physical price of computation.** Given an operation DAG it counts
the **logically-irreversible bit-erasures**, derives the **energy floor in joules**
(`erasures · k_B·T·ln2`, ≈ 2.85 zJ per bit at 300 K), the **Bennett reversible lower
bound** (necessary vs wasteful erasures) and a `0..1` **thermodynamic efficiency**. The
same principle that says erasing one bit must dissipate at least `kT·ln2` of heat —
the bridge between information and the second law.

Built on **`oracle-core`** (AIMarket Protocol v2). Where [Chronos](../chronos) proves
elapsed *time* (a VDF), Landauer computes an *entropic / thermal* floor — an orthogonal
quantity. It neither optimizes nor checks correctness; it audits irreversible
energetics.

```bash
# Audit: a 3-input AND tree (two AND gates) erases 2 bits → ~5.7 zJ at 300 K
curl -s -X POST http://localhost:9309/ai-market/v2/invoke -H "Content-Type: application/json" \
  -d '{"capability_id":"landauer.audit@v1","input":{"ops":[
        {"id":"a","gate":"input"},{"id":"b","gate":"input"},{"id":"c","gate":"input"},
        {"id":"g1","gate":"and","inputs":["a","b"]},
        {"id":"g2","gate":"and","inputs":["g1","c"]},
        {"id":"out","gate":"output","inputs":["g2"]}]}}'
```

| Capability | What | Price |
|---|---|---|
| `landauer.audit@v1` | irreversible_bits, energy_floor_j, reversible/wasteful bits, efficiency, circuit_commitment | $0.01 |
| `landauer.verify@v1` | trustless replay — recompute the erasure count + floor and check a claim | $0.001 |

**Verifiable, not asserted.** The audit is a pure function of a SHA-256
`circuit_commitment`; the irreversibility of each gate is `log2` of the collapse in
distinguishable states (fan-in bit loss), summed over a deterministic topological
traversal to an **integer**. Any verifier replays the count and reproduces
`energy_floor_j` bit-for-bit. It is a proof about the geometry of information, not a
hardware measurement.

Full physics, math, diagrams and use cases: [docs/en.md](docs/en.md) ·
[docs/ru.md](docs/ru.md) · [docs/es.md](docs/es.md).

Part of the [AICOM oracle family](https://github.com/alexar76/oracles). MIT.
