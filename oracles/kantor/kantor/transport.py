"""Kantor — exact discrete optimal transport (Wasserstein) with a dual certificate.

KANTOR answers the question an autonomous agent faces whenever it must compare,
match or move *distributions* rather than points: *what is the cheapest way to
turn distribution ``a`` into distribution ``b`` under a cost ``C`` — and can I be
**sure** it is the cheapest, before I pay for it?*

This is the discrete **Kantorovich optimal-transport** problem

    minimise   sum_ij  P_ij * C_ij
    over        P >= 0
    subject to  sum_j P_ij = a_i   (all the mass of source i is shipped)
                sum_i P_ij = b_j   (every sink j receives its demand)

— the *earth-mover's distance*. Its **Lagrangian dual** introduces a potential
``u_i`` on every source and ``v_j`` on every sink (Kantorovich potentials):

    maximise   sum_i a_i*u_i + sum_j b_j*v_j
    subject to u_i + v_j <= C_ij   for ALL i, j      (dual feasibility)

and LP strong duality says the two optima coincide, with **complementary
slackness** ``P_ij > 0  =>  u_i + v_j = C_ij`` on the support of the optimal plan.

This is the optimal-transport analogue of FERMAT's least-time dual certificate: there
the eikonal potential ``T(v)`` witnesses shortest-path optimality and a verifier
checks ``T(v) <= T(u)+n(u,v)`` on every edge; here the Kantorovich potentials
``(u, v)`` witness transport optimality and a verifier checks ``u_i + v_j <= C_ij``
on every (i, j) pair plus strong duality ``cost == sum a_i u_i + sum b_j v_j`` — in
O(m*n), without ever re-solving the transport problem and without trusting us.

EXACT solver (NOT Sinkhorn). We do *not* use ``scipy.optimize.linprog`` (scipy is
unavailable) nor entropic regularisation for the exact path. Instead the transport LP
is a **minimum-cost-flow** problem on a bipartite network, which we solve exactly in
pure Python by **successive shortest paths** (one Bellman-Ford to seed potentials,
then Dijkstra on reduced costs). The integer node potentials produced by min-cost flow
are *exactly* the LP duals — so the dual certificate falls out of the solver for free,
no separate dual solve required.

    a, b -> integer supplies/demands at a common scale Q (rounding fixed so the
            totals match exactly);
    network  S -> src_i (cap a_i, cost 0);  src_i -> sink_j (cap inf,
            cost round(C_ij * COST_SCALE));  sink_j -> T (cap b_j, cost 0);
    solve   min-cost max-flow S->T (saturates because total supply == total demand);
    plan    P_ij = flow(src_i -> sink_j) / Q;
    cost    sum_ij P_ij * C_ij  (recomputed from the float cost, not the rounded one);
    duals   u_i, v_j rescaled from the integer node potentials back to cost units.

For the p-Wasserstein distance the caller supplies points and a metric; with the
*default* squared-Euclidean ground cost the transport cost is ``W_p^p`` and we report
``W_p = cost ** (1/p)``. An explicitly-labelled **approximate Sinkhorn** path
(entropic regularisation, parameter ``eps``) is also offered and is *never* passed off
as exact: its result carries ``method="sinkhorn-approx"`` and the regulariser, and its
objective is always >= the true optimum (entropic OT upper-bounds OT).

Everything is deterministic and replayable. Ties are broken by a fixed rule (lowest
index) so any verifier reconstructs the identical answer from the same input.
"""

from __future__ import annotations

import heapq
from typing import Any

import numpy as np

# --- Compute bounds. The protocol layer does NOT validate against input_schema, so
# the handlers clamp here. Min-cost flow on a dense bipartite graph is the cost;
# m*n edges with successive-shortest-paths stays comfortably sub-second at these caps.
MAX_BINS = 64           # cap on #source bins and #sink bins (each)
MAX_DIM = 32            # cap on point dimensionality
MAX_SINKHORN_ITERS = 5000

# Mass is quantised to integer supplies/demands at this scale, costs to integers at
# COST_SCALE for the flow. Q is large so the residual quantisation error in the dual
# objective (~ max|potential| / Q) sits well below the verify tolerance — the certified
# cost and the dual objective then agree to float precision on the continuous marginals.
Q = 10_000_000         # mass quantisation (supplies/demands)
COST_SCALE = 1_000_000  # cost quantisation (integer edge costs for min-cost flow)

# Numerical tolerance for the dual-certificate comparisons (costs are floats).
EPS = 1e-9


# ---------------------------------------------------------------------------
# Input parsing / validation
# ---------------------------------------------------------------------------
def _as_float_vec(x: Any, name: str) -> np.ndarray:
    if x is None:
        raise ValueError(f"missing '{name}'")
    try:
        v = np.asarray(x, dtype=float).ravel()
    except (TypeError, ValueError):
        raise ValueError(f"'{name}' must be a numeric array")
    if v.size == 0:
        raise ValueError(f"'{name}' must be non-empty")
    if not np.all(np.isfinite(v)):
        raise ValueError(f"'{name}' must be finite")
    return v


def _normalise_weights(w: np.ndarray, name: str) -> np.ndarray:
    """Clamp negatives away and renormalise to a probability vector (sums to 1)."""
    if np.any(w < -EPS):
        raise ValueError(f"'{name}' weights must be non-negative")
    w = np.clip(w, 0.0, None)
    s = float(w.sum())
    if s <= EPS:
        raise ValueError(f"'{name}' weights sum to zero")
    return w / s


def _points(x: Any, name: str) -> np.ndarray:
    pts = np.asarray(x, dtype=float)
    if pts.ndim == 1:
        pts = pts.reshape(-1, 1)
    if pts.ndim != 2:
        raise ValueError(f"'{name}' must be a 2-D array of points")
    if not np.all(np.isfinite(pts)):
        raise ValueError(f"'{name}' must be finite")
    if pts.shape[1] > MAX_DIM:
        raise ValueError(f"'{name}' dimensionality exceeds MAX_DIM={MAX_DIM}")
    return pts


def cost_matrix(
    source_points: Any,
    sink_points: Any,
    p: float = 2.0,
    metric: str = "euclidean",
) -> np.ndarray:
    """Ground-cost matrix C (m*n) from point coordinates.

    ``metric``:
      * ``"euclidean"``        — C_ij = ||x_i - y_j||_2 ** p   (p-th power of the
                                  Euclidean distance; the canonical p-Wasserstein cost,
                                  so the transport cost is W_p^p and W_p = cost**(1/p));
      * ``"sqeuclidean"``      — C_ij = ||x_i - y_j||_2 ** 2   (squared-Euclidean,
                                  independent of p; the 2-Wasserstein-squared cost).
    """
    xs = _points(source_points, "source_points")
    ys = _points(sink_points, "sink_points")
    if xs.shape[1] != ys.shape[1]:
        raise ValueError("source_points and sink_points must share dimensionality")
    # pairwise squared Euclidean via the (a-b)^2 = a^2 - 2ab + b^2 identity
    sq = (
        (xs * xs).sum(1)[:, None]
        - 2.0 * xs @ ys.T
        + (ys * ys).sum(1)[None, :]
    )
    sq = np.clip(sq, 0.0, None)  # guard tiny negatives from float error
    if metric == "sqeuclidean":
        return sq
    if metric == "euclidean":
        return np.power(np.sqrt(sq), p)
    raise ValueError(f"unknown metric {metric!r} (use 'euclidean' or 'sqeuclidean')")


def _resolve_cost(d: dict[str, Any]) -> tuple[np.ndarray, float, str | None]:
    """Resolve the cost matrix C plus (p, metric) from either an explicit matrix or points.

    Returns ``(C, p, metric)`` where ``metric`` is None when C was given directly (so
    W_p reporting is suppressed unless the caller also told us the cost is a p-th power).
    """
    p = float(d.get("p", 2.0))
    if p <= 0:
        raise ValueError("'p' must be positive")
    metric = str(d.get("metric", "euclidean"))

    if d.get("cost") is not None:
        C = np.asarray(d["cost"], dtype=float)
        if C.ndim != 2:
            raise ValueError("'cost' must be a 2-D matrix")
        if not np.all(np.isfinite(C)):
            raise ValueError("'cost' must be finite")
        if np.any(C < -EPS):
            raise ValueError("'cost' must be non-negative")
        # An explicit matrix is the ground cost itself; we don't assume it is a p-th
        # power of a distance, so we don't report a Wasserstein root for it.
        return C, p, None

    if d.get("source_points") is not None and d.get("sink_points") is not None:
        return cost_matrix(d["source_points"], d["sink_points"], p=p, metric=metric), p, metric

    raise ValueError("provide either 'cost' (matrix) or 'source_points'+'sink_points'")


def _validate_shapes(a: np.ndarray, b: np.ndarray, C: np.ndarray) -> None:
    m, n = a.size, b.size
    if m > MAX_BINS or n > MAX_BINS:
        raise ValueError(f"too many bins (max {MAX_BINS} sources and {MAX_BINS} sinks)")
    if C.shape != (m, n):
        raise ValueError(f"cost shape {C.shape} != (len(a)={m}, len(b)={n})")


# ---------------------------------------------------------------------------
# Mass quantisation — integer supplies/demands whose totals match exactly
# ---------------------------------------------------------------------------
def quantise(weights: np.ndarray, total: int = Q) -> list[int]:
    """Largest-remainder rounding of a probability vector to integers summing to ``total``.

    Floor every ``w_i * total`` then hand the leftover units (``total - sum floors``)
    to the bins with the largest fractional parts. This is exact (sums to ``total`` by
    construction) and deterministic; it guarantees the source and sink integer marginals
    are equal so the min-cost flow saturates.
    """
    scaled = weights * total
    floors = np.floor(scaled).astype(np.int64)
    remainder = int(total - int(floors.sum()))
    if remainder > 0:
        frac = scaled - floors
        # largest fractional parts first; ties broken by lowest index (stable sort)
        order = np.argsort(-frac, kind="stable")
        for k in range(remainder):
            floors[order[k]] += 1
    return [int(x) for x in floors]


# ---------------------------------------------------------------------------
# Min-cost flow (successive shortest paths with potentials) — the EXACT solver
# ---------------------------------------------------------------------------
class _MCMF:
    """Minimum-cost maximum-flow via successive shortest augmenting paths.

    Edges are stored as a flat list; ``graph[u]`` holds indices into it. Each edge has a
    reverse partner (residual). Node ``potential`` is maintained so every augmentation
    runs Dijkstra on **non-negative reduced costs** ``cost + pot[u] - pot[v]``. The final
    potentials are exactly the LP duals of the transport problem (up to the integer cost
    scale), which is precisely the Kantorovich dual certificate.
    """

    def __init__(self, n_nodes: int) -> None:
        self.n = n_nodes
        self.to: list[int] = []
        self.cap: list[int] = []
        self.cost: list[int] = []
        self.graph: list[list[int]] = [[] for _ in range(n_nodes)]

    def add_edge(self, u: int, v: int, cap: int, cost: int) -> None:
        self.graph[u].append(len(self.to))
        self.to.append(v); self.cap.append(cap); self.cost.append(cost)
        self.graph[v].append(len(self.to))
        self.to.append(u); self.cap.append(0); self.cost.append(-cost)

    def _bellman_ford(self, s: int, pot: list[int]) -> None:
        """Seed potentials with one Bellman-Ford (handles the cost-0 structural edges)."""
        INF = float("inf")
        dist = [INF] * self.n
        dist[s] = 0
        for _ in range(self.n - 1):
            changed = False
            for u in range(self.n):
                if dist[u] == INF:
                    continue
                du = dist[u]
                for e in self.graph[u]:
                    if self.cap[e] > 0:
                        v = self.to[e]
                        nd = du + self.cost[e]
                        if nd < dist[v]:
                            dist[v] = nd
                            changed = True
            if not changed:
                break
        for v in range(self.n):
            pot[v] = 0 if dist[v] == INF else int(dist[v])

    def solve(self, s: int, t: int) -> int:
        """Push max flow s->t at min cost; return total flow. Potentials left in ``self.pot``."""
        INF = float("inf")
        pot = [0] * self.n
        self._bellman_ford(s, pot)
        total_flow = 0
        while True:
            # Dijkstra on reduced costs from s.
            dist = [INF] * self.n
            dist[s] = 0
            prev_edge = [-1] * self.n
            pq: list[tuple[int, int]] = [(0, s)]
            while pq:
                d, u = heapq.heappop(pq)
                if d > dist[u]:
                    continue
                for e in self.graph[u]:
                    if self.cap[e] <= 0:
                        continue
                    v = self.to[e]
                    nd = d + self.cost[e] + pot[u] - pot[v]
                    if nd < dist[v]:
                        dist[v] = nd
                        prev_edge[v] = e
                        heapq.heappush(pq, (nd, v))
            if dist[t] == INF:
                break  # no more augmenting path
            # update potentials by the true shortest-path distances
            for v in range(self.n):
                if dist[v] < INF:
                    pot[v] += int(dist[v])
            # bottleneck along the path t<-s
            push = INF
            v = t
            while v != s:
                e = prev_edge[v]
                push = min(push, self.cap[e])
                v = self.to[e ^ 1]
            push = int(push)
            v = t
            while v != s:
                e = prev_edge[v]
                self.cap[e] -= push
                self.cap[e ^ 1] += push
                v = self.to[e ^ 1]
            total_flow += push
        self.pot = pot
        return total_flow


def solve_exact(a: np.ndarray, b: np.ndarray, C: np.ndarray) -> dict[str, Any]:
    """Exact discrete optimal transport via min-cost flow. Returns plan, cost, duals.

    The node potentials from min-cost flow are the LP duals. With node layout
    ``S=0, src_i=1+i, sink_j=1+m+j, T=1+m+n`` and structural cost-0 edges S->src and
    sink->T, the shortest-path potentials satisfy, on every used src->sink edge,
    ``pot[sink_j] = pot[src_i] + round(C_ij*COST_SCALE)``. The Kantorovich potentials are

        u_i = -pot[src_i] / COST_SCALE       (rescaled to cost units)
        v_j =  pot[sink_j] / COST_SCALE

    so that on the support ``u_i + v_j = (pot[sink_j] - pot[src_i]) / COST_SCALE = C_ij``
    and ``u_i + v_j <= C_ij`` for all i,j (the reduced costs are non-negative), with
    ``sum a_i u_i + sum b_j v_j == optimal cost``. We then snap the duals to satisfy
    feasibility exactly under float rounding and re-derive the dual objective.
    """
    m, n = a.size, b.size
    supply = quantise(a, Q)
    demand = quantise(b, Q)
    # totals are both Q by construction of `quantise`

    S = 0
    src0 = 1
    snk0 = 1 + m
    T = 1 + m + n
    mc = _MCMF(2 + m + n)
    for i in range(m):
        mc.add_edge(S, src0 + i, supply[i], 0)
    for j in range(n):
        mc.add_edge(snk0 + j, T, demand[j], 0)
    # src_i -> sink_j : capacity Q (effectively unbounded for this flow), integer cost
    cscale = [[int(round(C[i, j] * COST_SCALE)) for j in range(n)] for i in range(m)]
    src_sink_edge: dict[tuple[int, int], int] = {}
    for i in range(m):
        for j in range(n):
            src_sink_edge[(i, j)] = len(mc.to)
            mc.add_edge(src0 + i, snk0 + j, Q, cscale[i][j])

    flow = mc.solve(S, T)
    # recover the plan from residual capacities on the forward src->sink edges
    P = np.zeros((m, n), dtype=float)
    flow_int = np.zeros((m, n), dtype=np.int64)
    for i in range(m):
        for j in range(n):
            e = src_sink_edge[(i, j)]
            f = Q - mc.cap[e]  # forward cap started at Q; used flow is Q - remaining
            flow_int[i, j] = f
            P[i, j] = f / Q

    cost = float(np.sum(P * C))

    # --- Kantorovich potentials from the min-cost-flow node potentials -------------
    pot = mc.pot
    u = np.array([-pot[src0 + i] for i in range(m)], dtype=float) / COST_SCALE
    v = np.array([pot[snk0 + j] for j in range(n)], dtype=float) / COST_SCALE

    # Snap duals to be exactly feasible under float rounding: shift each v_j down to the
    # tightest residual slack so u_i + v_j <= C_ij holds for ALL i,j. The relation is
    # preserved on the support (where slack is ~0), so strong duality is unharmed.
    slack = C - (u[:, None] + v[None, :])
    min_slack = float(slack.min())
    if min_slack < 0:
        # distribute the (tiny, rounding-scale) infeasibility off the v potentials
        v = v + min_slack  # uniform shift keeps complementary slackness on the support
    dual_obj = float(np.dot(a, u) + np.dot(b, v))

    return {
        "plan": P,
        "flow_int": flow_int,
        "cost": cost,
        "u": u,
        "v": v,
        "dual_objective": dual_obj,
        "flow": flow,
        "supply": supply,
        "demand": demand,
    }


# ---------------------------------------------------------------------------
# Sinkhorn — the explicitly APPROXIMATE entropic-OT path
# ---------------------------------------------------------------------------
def solve_sinkhorn(
    a: np.ndarray,
    b: np.ndarray,
    C: np.ndarray,
    eps: float = 0.1,
    iters: int = 1000,
    tol: float = 1e-9,
) -> dict[str, Any]:
    """Entropic-regularised OT (Sinkhorn-Knopp). APPROXIMATE — never exact.

    Minimises ``<P,C> - eps*H(P)`` by matrix scaling on the Gibbs kernel
    ``K = exp(-C/eps)``. Its transport objective ``<P,C>`` is an **upper bound** on the
    true optimum (entropy is subtracted in the regularised objective, so the unregularised
    cost of the regularised solution is >= the true OT cost) and converges to it only as
    ``eps -> 0``. Returned with ``method="sinkhorn-approx"`` and the regulariser so it is
    never mistaken for the certified-exact answer.
    """
    if eps <= 0:
        raise ValueError("'eps' must be positive")
    iters = min(int(iters), MAX_SINKHORN_ITERS)
    K = np.exp(-C / eps)
    # guard against underflow producing an all-zero column/row
    K = np.maximum(K, 1e-300)
    u_s = np.ones(a.size)
    v_s = np.ones(b.size)
    for _ in range(iters):
        u_prev = u_s
        u_s = a / (K @ v_s)
        v_s = b / (K.T @ u_s)
        if np.max(np.abs(u_s - u_prev)) < tol:
            break
    P = u_s[:, None] * K * v_s[None, :]
    cost = float(np.sum(P * C))
    # entropic dual potentials (in cost units): f = eps*log(u), g = eps*log(v)
    f = eps * np.log(np.maximum(u_s, 1e-300))
    g = eps * np.log(np.maximum(v_s, 1e-300))
    return {
        "plan": P,
        "cost": cost,
        "u": f,
        "v": g,
        "eps": float(eps),
    }


# ---------------------------------------------------------------------------
# Public handlers (called by capabilities.py)
# ---------------------------------------------------------------------------
def transport(d: dict[str, Any]) -> dict[str, Any]:
    """Full KANTOR computation — the ``kantor.transport@v1`` handler core.

    Solves the exact OT problem (default) or the approximate Sinkhorn path, returning the
    transport plan, the optimal cost, the Wasserstein distance (when the ground cost is a
    p-th power of a metric), and the Kantorovich dual potentials (u, v) — the certificate.
    """
    a = _normalise_weights(_as_float_vec(d.get("a"), "a"), "a")
    b = _normalise_weights(_as_float_vec(d.get("b"), "b"), "b")
    C, p, metric = _resolve_cost(d)
    _validate_shapes(a, b, C)

    method = str(d.get("method", "exact")).lower()
    if method in ("exact", "mincostflow", "min-cost-flow"):
        res = solve_exact(a, b, C)
        out_method = "exact-mincostflow"
        cost = res["cost"]
        u, v = res["u"], res["v"]
        plan = res["plan"]
        dual_obj = res["dual_objective"]
    elif method in ("sinkhorn", "sinkhorn-approx", "approx"):
        eps = float(d.get("eps", 0.1))
        res = solve_sinkhorn(a, b, C, eps=eps)
        out_method = "sinkhorn-approx"
        cost = res["cost"]
        u, v = res["u"], res["v"]
        plan = res["plan"]
        dual_obj = float(np.dot(a, u) + np.dot(b, v))
    else:
        raise ValueError(f"unknown method {method!r} (use 'exact' or 'sinkhorn')")

    out: dict[str, Any] = {
        "method": out_method,
        "cost": round(cost, 12),
        "plan": [[round(float(x), 12) for x in row] for row in plan],
        "potentials": {
            "u": [round(float(x), 12) for x in u],
            "v": [round(float(x), 12) for x in v],
        },
        "dual_objective": round(dual_obj, 12),
        "m": int(a.size),
        "n": int(b.size),
        "p": p,
        "metric": metric,
    }
    # Report the p-Wasserstein distance only when the ground cost is a p-th power of a
    # metric (points + euclidean): then transport cost == W_p^p and W_p = cost**(1/p).
    if metric == "euclidean":
        out["wasserstein"] = round(float(cost) ** (1.0 / p) if cost > 0 else 0.0, 12)
    elif metric == "sqeuclidean":
        # squared-Euclidean ground cost == W_2^2 regardless of p; report W_2.
        out["wasserstein"] = round(float(cost) ** 0.5 if cost > 0 else 0.0, 12)
    else:
        out["wasserstein"] = None

    if out_method == "sinkhorn-approx":
        out["regularizer_eps"] = res["eps"]
        out["approximate"] = True
        out["note"] = (
            "ENTROPIC (Sinkhorn) approximation: cost is an upper bound on the true "
            "optimum and converges to it only as eps -> 0. Not certified-exact; for a "
            "verifiable dual certificate use method='exact'."
        )
    else:
        out["approximate"] = False
        out["certificate"] = {
            "kind": "kantorovich-lp-dual-complementary-slackness",
            "feasibility": "u_i + v_j <= C_ij for every (i,j)",
            "strong_duality": "cost == sum_i a_i*u_i + sum_j b_j*v_j",
            "note": (
                "dual feasibility on every pair + strong duality => the transport cost is "
                "globally optimal; checkable in O(m*n) via kantor.verify, no re-solve."
            ),
        }
    return out


def verify(d: dict[str, Any]) -> dict[str, Any]:
    """Trustless dual-certificate check — the ``kantor.verify@v1`` handler core.

    Given ``a, b, C`` (or points), a ``claimed_cost`` and Kantorovich potentials
    ``(u, v)``, confirm optimality in O(m*n) WITHOUT re-solving the transport problem:

      * DUAL FEASIBILITY  ``u_i + v_j <= C_ij + tol`` for ALL i, j (the only place the
        whole cost matrix is touched — no shortcut exists);
      * STRONG DUALITY    ``claimed_cost ≈ sum_i a_i*u_i + sum_j b_j*v_j`` within tol.

    Both holding certifies ``claimed_cost`` as the exact optimal transport cost (LP weak
    duality bounds any feasible primal from below by any feasible dual; equality pins the
    optimum). Returns ``{valid, dual_objective, claimed_cost, max_violation}``.
    """
    a = _normalise_weights(_as_float_vec(d.get("a"), "a"), "a")
    b = _normalise_weights(_as_float_vec(d.get("b"), "b"), "b")
    C, _p, _metric = _resolve_cost(d)
    _validate_shapes(a, b, C)

    pot = d.get("potentials")
    if not isinstance(pot, dict):
        raise ValueError("missing 'potentials' object {u, v}")
    u = _as_float_vec(pot.get("u"), "potentials.u")
    v = _as_float_vec(pot.get("v"), "potentials.v")
    if u.size != a.size or v.size != b.size:
        raise ValueError("potential lengths must match len(a) and len(b)")

    if d.get("claimed_cost") is None:
        raise ValueError("missing 'claimed_cost'")
    claimed_cost = float(d["claimed_cost"])

    # tolerance scales with the cost magnitude so it is robust to the input units
    scale = max(1.0, float(np.max(np.abs(C))) if C.size else 1.0)
    tol = float(d.get("tol", 1e-6)) * scale

    # --- dual feasibility: u_i + v_j <= C_ij on every pair (the O(m*n) sweep) ------
    violation = (u[:, None] + v[None, :]) - C  # > 0 means infeasible
    max_violation = float(violation.max()) if violation.size else 0.0
    feasible = max_violation <= tol

    # --- strong duality: claimed_cost == dual objective ---------------------------
    dual_obj = float(np.dot(a, u) + np.dot(b, v))
    duality_gap = abs(claimed_cost - dual_obj)
    duality_ok = duality_gap <= tol

    valid = bool(feasible and duality_ok)
    return {
        "valid": valid,
        "feasible": bool(feasible),
        "strong_duality": bool(duality_ok),
        "dual_objective": round(dual_obj, 12),
        "claimed_cost": round(claimed_cost, 12),
        "max_violation": round(max_violation, 12),
        "duality_gap": round(duality_gap, 12),
        "m": int(a.size),
        "n": int(b.size),
        "note": (
            "dual feasibility (u_i+v_j<=C_ij on every pair) + strong duality "
            "(claimed_cost==sum a_i u_i + sum b_j v_j) => claimed_cost is the exact "
            "optimal transport cost. Checked in O(m*n), no re-solve, no trust in the oracle."
        ),
    }
