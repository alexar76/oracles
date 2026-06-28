# Kantor — Optimal-Transport (Wasserstein) Oracle 🪨

**Kantor sells the proof, not just the plan.** Given a source distribution `a`, a sink
distribution `b` and a ground cost `C` (supplied directly, or computed from point
coordinates for the **p-Wasserstein** `W_p`), it solves the discrete **Kantorovich
optimal-transport** problem *exactly* and returns the optimal transport plan `P`, the
cost, and the **Kantorovich dual potentials** `(u, v)` — a certificate any client can
check in **O(m·n)** to confirm the cost is *globally optimal*, **without re-solving and
without trusting the oracle.**

This is the optimal-transport analogue of [Fermat](../fermat)'s least-time dual
certificate: there the eikonal potential `T(v)` witnesses shortest-path optimality;
here the Kantorovich potentials `(u, v)` witness transport optimality.

```
minimise  Σ_ij P_ij·C_ij     subject to  row sums(P) = a,  col sums(P) = b,  P ≥ 0
dual:     maximise  Σ_i a_i·u_i + Σ_j b_j·v_j     s.t.  u_i + v_j ≤ C_ij  for all i,j
```

## Exact, by min-cost flow (no Sinkhorn, no scipy)

The transport LP is a **minimum-cost-flow** problem on a bipartite network, solved
*exactly* in pure Python by **successive shortest paths** (one Bellman-Ford to seed node
potentials, then Dijkstra on reduced costs). The integer node potentials produced by the
flow **are** the LP duals — so the Kantorovich certificate falls out of the solver for
free. Mass is quantised to integer supplies/demands at a common scale `Q` with
largest-remainder rounding so the marginals match exactly.

An **explicitly approximate** entropic **Sinkhorn** path is also offered
(`method:"sinkhorn"`, regulariser `eps`); its objective is an *upper bound* on the true
optimum and it is returned as `method:"sinkhorn-approx"` — never passed off as exact.

```bash
# Exact transport: the 2x2 "swap" case, optimal cost 0.2
curl -s -X POST http://localhost:9314/ai-market/v2/invoke -H "Content-Type: application/json" \
  -d '{"capability_id":"kantor.transport@v1","input":{"a":[0.6,0.4],"b":[0.4,0.6],"cost":[[0,1],[1,0]]}}'

# p-Wasserstein from points (default squared-Euclidean via euclidean, p=2): W_2 = 0.4
curl -s -X POST http://localhost:9314/ai-market/v2/invoke -H "Content-Type: application/json" \
  -d '{"capability_id":"kantor.transport@v1","input":{"a":[0.5,0.5],"b":[0.5,0.5],"source_points":[[0],[1]],"sink_points":[[0.4],[0.6]]}}'
```

| Capability | What | Price |
|---|---|---|
| `kantor.transport@v1` | exact OT plan + cost + `W_p` + Kantorovich dual potentials `(u,v)` | $0.006 |
| `kantor.verify@v1` | trustless O(m·n) dual-certificate check | $0.001 |

## Verifiable by duality, not asserted

`kantor.verify` re-derives the ground cost and checks, in one O(m·n) sweep:

* **dual feasibility** `u_i + v_j ≤ C_ij` on *every* `(i,j)` pair (no shortcut exists), and
* **strong duality** `claimed_cost = Σ_i a_i·u_i + Σ_j b_j·v_j`.

Both holding certifies `claimed_cost` as the exact optimal transport cost (LP weak
duality bounds any feasible primal from below by any feasible dual; equality pins the
optimum). Returns `{valid, dual_objective, claimed_cost, max_violation}` — no re-solve,
no trust in the oracle.

Built on **`oracle-core`** (AIMarket Protocol v2). Part of the
[AICOM oracle family](https://github.com/alexar76/oracles). MIT.
