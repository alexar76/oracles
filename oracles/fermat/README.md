# Fermat — Least-Time Routing Oracle 🔦

**Fermat sells the proof, not just the path.** Given a directed weighted service
graph, a `start` and a `goal`, it returns the **globally least-"time" composition
path** plus a **dual optimality certificate**: the eikonal potential `T(v)` for every
node, which any client can check in O(E) to confirm the path is *globally optimal* —
**without re-running the search and without trusting the oracle.**

Each edge is a **refractive index** `n(u,v) ≥ 0` blending cost + latency +
`(1 − reputation)`. By **Fermat's principle of least time**, the optimal composition
is the optical ray that minimises total optical length; its discrete optimality
condition is the **eikonal / Bellman relation** `T(v) = min_u T(u) + n(u,v)`.

Built on **`oracle-core`** (AIMarket Protocol v2). Unlike [Colony](../colony) (a
*heuristic* TSP solver that returns an optimality *gap*), Fermat returns a **provably
exact** optimum on a weighted graph with a checkable certificate.

```bash
# Route: diamond graph, optimal is s -> a -> t with total 2
curl -s -X POST http://localhost:9307/ai-market/v2/invoke -H "Content-Type: application/json" \
  -d '{"capability_id":"fermat.route@v1","input":{"edges":[["s","a",1],["a","t",1],["s","b",1],["b","t",5],["s","t",10]],"start":"s","goal":"t"}}'
```

| Capability | What | Price |
|---|---|---|
| `fermat.route@v1` | least-time path + total + eikonal potentials `T(v)` + dual certificate | $0.01 |
| `fermat.verify@v1` | trustless O(E) certificate check — feasibility on every edge, tightness on the path | $0.001 |

**Verifiable by duality, not asserted.** The computation is a pure function of a
SHA-256 `graph_commitment`. The certificate is the LP dual / complementary-slackness
witness: a verifier confirms

* **feasibility** `T(v) ≤ T(u) + n(u,v)` on *every* edge (no shortcut exists), and
* **tightness** `T(v) = T(u) + n(u,v)` on *every* edge of the returned path (the ray
  is stationary — Snell's law),

and thereby proves global optimality in one O(E) pass — never re-running Dijkstra.

Full math, diagrams and use cases: [docs/en.md](docs/en.md) · [docs/ru.md](docs/ru.md) · [docs/es.md](docs/es.md).

Part of the [AICOM oracle family](https://github.com/alexar76/oracles). MIT.
