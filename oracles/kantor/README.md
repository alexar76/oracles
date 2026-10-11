# Kantor — Optimal-Transport (Wasserstein) Oracle 🪨

**Kantor sells the proof, not just the plan.** Given a source distribution `a`, a sink
distribution `b` and a ground cost `C` (supplied directly, or computed from point
coordinates for the **p-Wasserstein** `W_p`), it solves the discrete **Kantorovich
optimal-transport** problem *exactly* and returns the optimal transport plan `P`, the
cost, and the **Kantorovich dual potentials** `(u, v)`. The plan and potentials together
form a two-sided certificate any client can check in **O(m·n)** to confirm the cost is
*globally optimal*, **without re-solving and without trusting the oracle** — the plan
bounds the optimum from above, the potentials from below, and they meet at the cost.

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
| `kantor.transport@v1` | exact OT plan `P` + cost + `W_p` + Kantorovich dual potentials `(u,v)` | $0.006 |
| `kantor.verify@v1` | trustless O(m·n) **primal-dual** certificate check | $0.001 |

## Verifiable by duality, not asserted — but both sides are required

A dual certificate alone is **not** enough. By LP weak duality any dual-feasible `(u,v)`
gives `Σ a_i·u_i + Σ b_j·v_j ≤ optimal_cost` — a **lower** bound only. So a dual-only
check (feasibility + `claimed_cost = dual_objective`) would accept *any* `claimed_cost`
equal to a feasible-but-suboptimal dual value, and could not catch an **under-reported**
cost: with `u = v = 0` the dual is feasible whenever `C ≥ 0` and its objective is `0`, so
a dishonest oracle could otherwise "prove" a cost of `0` (or negative).

`kantor.verify` therefore requires **both** the plan `P` and the potentials `(u,v)`, and
checks, in one O(m·n) sweep:

* **primal feasibility** `P ≥ 0`, `row-sums(P) = a`, `col-sums(P) = b`, and
  `⟨P,C⟩ = claimed_cost` — a feasible plan, so its cost is an **upper** bound; and
* **dual feasibility** `u_i + v_j ≤ C_ij` on *every* `(i,j)` pair (no shortcut exists),
  with **strong duality** `claimed_cost = Σ_i a_i·u_i + Σ_j b_j·v_j` — a **lower** bound.

Upper bound `= lower bound = claimed_cost` pins the exact optimum (and a transport cost is
`≥ 0`, so a negative claim is rejected outright). Returns
`{valid, feasible, strong_duality, primal_feasible, primal_cost_matches, dual_objective,
primal_cost, claimed_cost, max_violation, …}` — no re-solve, no trust in the oracle.

Built on **`oracle-core`** (AIMarket Protocol v2). Part of the
[AICOM oracle family](https://github.com/alexar76/oracles). MIT.
