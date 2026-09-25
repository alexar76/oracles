"""Fermat — provably-optimal routing/composition by the principle of least time.

FERMAT answers the question an autonomous agent faces every time it must assemble a
paid pipeline out of other agents' capabilities: *what is the cheapest legal way to
get from where I am to the result I want — and can I be **sure** it is the cheapest,
before I pay for it?*

It treats a directed service graph as an **optical medium**. Each edge ``(u, v)`` is
assigned a non-negative **refractive index** ``n(u, v)`` — a blend of money cost,
latency and risk ``(1 - reputation)``. A composition path is then a ray of light, and
its total "optical length" is its total time/cost. **Fermat's principle of least
time** says the physical ray between two points is the one that makes the optical
length *stationary*; for a non-negative medium that stationary path is the global
minimum. The discrete analogue of the continuous variational condition
``δ ∫ n · ds = 0`` is exactly the shortest-path optimality condition, and the
discrete analogue of the **eikonal equation** ``|∇T| = n`` is the Bellman relation

    T(v) = min over incoming edges (u, v) of  T(u) + n(u, v),

where ``T`` is the eikonal potential — the least cost-to-reach. Snell's law (a ray
bends at an interface to keep the path stationary) is the *local* tightness condition
on the chosen path. FERMAT computes ``T`` and the optimal ray with Dijkstra, and —
this is its strongest feature — ships a **dual certificate** so a verifier can confirm
global optimality in O(E) *without re-running Dijkstra*:

1. **Canonicalisation.** The graph is normalised (sorted nodes, sorted edges, parallel
   edges reduced to the cheapest, non-negative weights) and hashed to a
   ``graph_commitment`` (SHA-256). The whole computation is a pure function of that
   committed graph plus ``(start, goal, blend)``.
2. **Compute (the ray).** Dijkstra from ``start`` over non-negative indices yields the
   potential ``T(v)`` for every node and the least-cost path to ``goal``.
3. **Certificate (the proof).** ``T`` is itself the LP-dual / complementary-slackness
   witness. A verifier checks, in one pass over the edges:
     * FEASIBILITY  ``T(v) <= T(u) + n(u, v)``  for **every** edge (the eikonal
       inequality / dual feasibility — no shortcut exists);
     * TIGHTNESS    ``T(v) == T(u) + n(u, v)``  on **every** edge of the returned
       path (Snell stationarity — the ray actually realises its potential).
   Feasibility + tightness ⇒ the path is globally optimal by shortest-path /
   LP-duality optimality conditions. The proof is *checked*, never trusted.

Everything is deterministic and replayable. There is no oracle-controlled randomness;
ties are broken by a fixed rule (lowest node index), so any verifier reconstructs the
identical potentials and ray from the committed graph alone.
"""

from __future__ import annotations

import hashlib
import heapq
import json
from typing import Any

# Bound compute so one call cannot stall the service. Dijkstra is O(E log V); the
# certificate check is O(E). These caps keep both comfortably sub-second.
MAX_NODES = 5000
MAX_EDGES = 50000

# Numerical tolerance for the tightness / feasibility comparisons (weights are floats).
EPS = 1e-9

# Default refractive-index blend  n = a*cost + b*latency_norm + c*(1 - reputation).
# Latency is normalised to seconds-ish scale by /1000 so a millisecond figure and a
# dollar figure live on a comparable order; callers may override the whole blend.
DEFAULT_BLEND = {"cost": 1.0, "latency": 1.0, "reputation": 1.0, "latency_scale": 1000.0}


def _num(x: Any, name: str, *, lo: float | None = None) -> float:
    try:
        v = float(x)
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be a number, got {x!r}")
    if v != v or v in (float("inf"), float("-inf")):
        raise ValueError(f"{name} must be finite")
    if lo is not None and v < lo:
        raise ValueError(f"{name} must be >= {lo}")
    return v


def edge_index(weight_fields: dict[str, Any], blend: dict[str, float]) -> float:
    """Refractive index n(u,v) >= 0 for one edge from its component fields.

    ``weight_fields`` may carry ``cost``, ``latency`` and ``reputation``. The index is
    ``a*cost + b*(latency/latency_scale) + c*(1 - reputation)`` with the blend
    coefficients ``a,b,c``. Reputation is clamped to ``[0, 1]`` so ``1 - reputation``
    (the risk term) is always in ``[0, 1]`` and the whole index is non-negative — the
    physical requirement that a medium cannot have negative optical density (and the
    mathematical requirement for Dijkstra correctness).
    """
    a = float(blend.get("cost", 1.0))
    b = float(blend.get("latency", 1.0))
    c = float(blend.get("reputation", 1.0))
    scale = float(blend.get("latency_scale", 1000.0)) or 1.0

    cost = _num(weight_fields.get("cost", 0.0), "cost", lo=0.0)
    latency = _num(weight_fields.get("latency", 0.0), "latency", lo=0.0)
    rep = _num(weight_fields.get("reputation", 1.0), "reputation")
    rep = min(1.0, max(0.0, rep))  # clamp into [0,1]

    n = a * cost + b * (latency / scale) + c * (1.0 - rep)
    if n < 0:
        raise ValueError("refractive index n(u,v) must be non-negative")
    return n


def _normalise_edge(e: Any, blend: dict[str, float]) -> tuple[str, str, float, dict[str, Any]]:
    """Parse one input edge into ``(u, v, n, fields)``.

    Accepts two shapes:
      * a list/tuple ``[u, v, weight]`` (or ``[u, v]`` ⇒ weight 0) — ``weight`` is the
        already-blended non-negative refractive index;
      * a dict ``{"from"/"u": ..., "to"/"v": ..., "cost"?, "latency"?, "reputation"?,
        "weight"/"n"?}`` — if ``weight``/``n`` is present it is used directly, else the
        index is derived from the component fields via ``edge_index``.
    """
    if isinstance(e, dict):
        u = e.get("from", e.get("u", e.get("source")))
        v = e.get("to", e.get("v", e.get("target")))
        if u is None or v is None:
            raise ValueError("edge dict needs 'from'/'u' and 'to'/'v'")
        u, v = str(u), str(v)
        if "weight" in e or "n" in e:
            n = _num(e.get("weight", e.get("n")), "weight", lo=0.0)
            fields = {"weight": n}
        else:
            n = edge_index(e, blend)
            fields = {k: e[k] for k in ("cost", "latency", "reputation") if k in e}
        return u, v, n, fields
    if isinstance(e, (list, tuple)):
        if len(e) < 2:
            raise ValueError("list edge must be [u, v] or [u, v, weight]")
        u, v = str(e[0]), str(e[1])
        n = _num(e[2], "weight", lo=0.0) if len(e) >= 3 else 0.0
        return u, v, n, {"weight": n}
    raise ValueError(f"edge must be a list or dict, got {type(e).__name__}")


def canonical_graph(
    nodes: list[Any] | None,
    edges: list[Any],
    blend: dict[str, float],
) -> tuple[list[str], dict[str, int], list[list[tuple[int, float]]], list[tuple[int, int, float]], str]:
    """Normalise an arbitrary directed weighted graph to a canonical, hashable form.

    Returns ``(labels, index, adj, edge_list, commitment)``:
      * ``labels`` — sorted unique node identifiers (strings);
      * ``index`` — label → position;
      * ``adj`` — out-adjacency: ``adj[u]`` is a list of ``(v, n)``;
      * ``edge_list`` — sorted unique directed edges as ``(i, j, n)`` index triples
        (parallel edges collapsed to the **cheapest** index — light takes the fastest
        channel);
      * ``commitment`` — SHA-256 of canonical JSON
        ``{"nodes":[...], "edges":[[i,j,n],...], "directed":true}`` with ``n`` rounded
        to 12 decimals so the commitment is stable across float formatting.
    """
    if not isinstance(edges, list):
        raise ValueError("'edges' must be a list")
    if len(edges) > MAX_EDGES:
        raise ValueError(f"too many edges (max {MAX_EDGES})")

    label_set: set[str] = set(str(x) for x in (nodes or []))
    parsed: list[tuple[str, str, float]] = []
    for e in edges:
        u, v, n, _fields = _normalise_edge(e, blend)
        label_set.add(u)
        label_set.add(v)
        if u == v:
            continue  # drop self-loops — a least-time ray never revisits in place
        parsed.append((u, v, n))

    labels = sorted(label_set)
    if not labels:
        raise ValueError("graph has no nodes")
    if len(labels) > MAX_NODES:
        raise ValueError(f"too many nodes (max {MAX_NODES})")
    idx = {lab: i for i, lab in enumerate(labels)}

    # Collapse parallel edges to the minimum index (the cheapest available channel).
    best: dict[tuple[int, int], float] = {}
    for u, v, n in parsed:
        key = (idx[u], idx[v])
        if key not in best or n < best[key]:
            best[key] = n

    edge_list = sorted((a, b, best[(a, b)]) for (a, b) in best)
    adj: list[list[tuple[int, float]]] = [[] for _ in labels]
    for a, b, n in edge_list:
        adj[a].append((b, n))

    canon = {
        "nodes": labels,
        "edges": [[a, b, round(n, 12)] for a, b, n in edge_list],
        "directed": True,
    }
    commitment = hashlib.sha256(
        json.dumps(canon, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()
    return labels, idx, adj, edge_list, commitment


def dijkstra(adj: list[list[tuple[int, float]]], source: int, n_nodes: int) -> tuple[list[float], list[int]]:
    """Least-time potentials T and parent pointers from ``source`` (non-negative n).

    ``T[v]`` is the optical length of the least-time ray from ``source`` to ``v``
    (``inf`` if unreachable); ``parent[v]`` is the predecessor on that ray (``-1`` for
    the source and unreachable nodes). Ties are broken by lowest node index via the
    ``(dist, node)`` heap key, so the result is fully deterministic.
    """
    INF = float("inf")
    T = [INF] * n_nodes
    parent = [-1] * n_nodes
    T[source] = 0.0
    pq: list[tuple[float, int]] = [(0.0, source)]
    while pq:
        d, u = heapq.heappop(pq)
        if d > T[u] + EPS:
            continue
        for v, w in adj[u]:
            nd = d + w
            if nd < T[v] - EPS:
                T[v] = nd
                parent[v] = u
                heapq.heappush(pq, (nd, v))
    return T, parent


def reconstruct_path(parent: list[int], source: int, target: int) -> list[int] | None:
    """Walk parent pointers from ``target`` back to ``source``; None if disconnected."""
    if parent[target] == -1 and target != source:
        return None
    path = [target]
    cur = target
    seen = {target}
    while cur != source:
        cur = parent[cur]
        if cur == -1 or cur in seen:
            return None
        seen.add(cur)
        path.append(cur)
    path.reverse()
    return path


def potentials_dict(labels: list[str], T: list[float]) -> dict[str, float | None]:
    """Eikonal potential T(v) keyed by node label (None for unreachable nodes)."""
    out: dict[str, float | None] = {}
    for i, lab in enumerate(labels):
        out[lab] = None if T[i] == float("inf") else round(T[i], 12)
    return out


def route(
    nodes: list[Any] | None,
    edges: list[Any],
    start: Any,
    goal: Any,
    blend: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Full FERMAT computation — the ``fermat.route@v1`` handler core.

    Computes the eikonal potential T(v) for every node and the globally least-time
    composition path ``start → goal``, and emits the dual-certificate fields a
    verifier needs to confirm optimality in O(E).
    """
    blend = {**DEFAULT_BLEND, **(blend or {})}
    labels, idx, adj, edge_list, commitment = canonical_graph(nodes, edges, blend)
    n_nodes = len(labels)

    s, g = str(start), str(goal)
    if s not in idx:
        raise ValueError(f"start node {s!r} not in graph")
    if g not in idx:
        raise ValueError(f"goal node {g!r} not in graph")
    si, gi = idx[s], idx[g]

    T, parent = dijkstra(adj, si, n_nodes)
    reachable = T[gi] != float("inf")
    path_idx = reconstruct_path(parent, si, gi) if reachable else None
    path = [labels[i] for i in path_idx] if path_idx else None
    total = round(T[gi], 12) if reachable else None

    # Tightness edges of the returned ray: (u, v, n) the verifier must find T-tight.
    path_edges: list[list[Any]] = []
    if path_idx:
        weight_of = {(a, b): n for a, b, n in edge_list}
        for a, b in zip(path_idx, path_idx[1:]):
            path_edges.append([labels[a], labels[b], round(weight_of[(a, b)], 12)])

    return {
        "start": s,
        "goal": g,
        "reachable": reachable,
        "path": path,
        "total": total,
        "potentials": potentials_dict(labels, T),
        "graph_commitment": commitment,
        "n": n_nodes,
        "m": len(edge_list),
        "blend": {k: round(float(blend[k]), 12) for k in ("cost", "latency", "reputation", "latency_scale")},
        "certificate": {
            "kind": "lp-dual-complementary-slackness",
            "path_edges": path_edges,
            "feasibility": "T(v) <= T(u) + n(u,v) for every edge",
            "tightness": "T(v) == T(u) + n(u,v) on every path edge",
            "note": "feasibility + tightness => globally optimal by shortest-path/LP duality; checkable in O(E) without re-running Dijkstra.",
        },
    }


def verify(
    nodes: list[Any] | None,
    edges: list[Any],
    path: list[Any] | None,
    potentials: dict[str, Any],
    start: Any,
    goal: Any,
    total: float | None = None,
    blend: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Trustless certificate check — the ``fermat.verify@v1`` handler core.

    Re-derives the canonical graph (so it also re-derives ``graph_commitment`` and the
    refractive indices), then checks the supplied potentials ``T`` and ``path`` against
    the **dual optimality conditions** — in O(E), without running Dijkstra:

      * FEASIBILITY  ``T(v) <= T(u) + n(u,v)`` for every edge (no missed shortcut);
      * TIGHTNESS    ``T(v) == T(u) + n(u,v)`` on every edge of the path, the path
        starts at ``start``, ends at ``goal``, and ``T(start) == 0``.

    If both hold the path is globally optimal, ``valid`` is True, and the recomputed
    optimum ``T(goal)`` is returned (and matched against ``total`` if supplied).
    """
    blend = {**DEFAULT_BLEND, **(blend or {})}
    labels, idx, adj, edge_list, commitment = canonical_graph(nodes, edges, blend)
    s, g = str(start), str(goal)
    if s not in idx or g not in idx:
        raise ValueError("start/goal not in graph")

    # Materialise T over the canonical node set. Missing / null potentials are +inf.
    if not isinstance(potentials, dict):
        raise ValueError("'potentials' must be an object mapping node -> T(v)")
    T: list[float] = [float("inf")] * len(labels)
    for lab, val in potentials.items():
        key = str(lab)
        if key in idx and val is not None:
            T[idx[key]] = _num(val, f"T({key})")

    reasons: list[str] = []

    # --- Dual feasibility (the eikonal inequality holds on every edge) -------------
    feasible = True
    violations = 0
    first_violation: list[Any] | None = None
    for a, b, w in edge_list:
        # An edge out of an unreachable (inf) tail is vacuously feasible.
        if T[a] == float("inf"):
            continue
        if T[b] > T[a] + w + EPS:
            feasible = False
            violations += 1
            if first_violation is None:
                first_violation = [labels[a], labels[b], round(w, 12),
                                   round(T[a], 12), round(T[b], 12)]
    if not feasible:
        reasons.append(f"feasibility violated on {violations} edge(s)")

    # --- Source grounding: T(start) must be 0 -------------------------------------
    source_ok = abs(T[idx[s]] - 0.0) <= EPS
    if not source_ok:
        reasons.append("T(start) != 0")

    # --- Path tightness (Snell stationarity on the claimed ray) -------------------
    tight = True
    path_labels = [str(p) for p in path] if path else None
    if path_labels:
        if path_labels[0] != s or path_labels[-1] != g:
            tight = False
            reasons.append("path does not run start -> goal")
        else:
            wmap = {(a, b): w for a, b, w in edge_list}
            for x, y in zip(path_labels, path_labels[1:]):
                if x not in idx or y not in idx:
                    tight = False
                    reasons.append(f"path uses unknown node {x!r}/{y!r}")
                    break
                key = (idx[x], idx[y])
                if key not in wmap:
                    tight = False
                    reasons.append(f"path edge {x}->{y} not in graph")
                    break
                w = wmap[key]
                if T[idx[x]] == float("inf") or abs(T[idx[y]] - (T[idx[x]] + w)) > 1e-6:
                    tight = False
                    reasons.append(f"path edge {x}->{y} not T-tight")
                    break
    else:
        tight = False
        reasons.append("no path supplied")

    recomputed_total = None if T[idx[g]] == float("inf") else round(T[idx[g]], 12)
    total_ok = True
    if total is not None and recomputed_total is not None:
        total_ok = abs(float(total) - recomputed_total) <= 1e-6
        if not total_ok:
            reasons.append("claimed total != T(goal)")

    valid = bool(feasible and source_ok and tight and total_ok)
    return {
        "valid": valid,
        "feasible": bool(feasible),
        "tight": bool(tight),
        "source_grounded": bool(source_ok),
        "graph_commitment": commitment,
        "recomputed_total": recomputed_total,
        "claimed_total": (None if total is None else round(float(total), 12)),
        "first_violation": first_violation,
        "edges_checked": len(edge_list),
        "reasons": reasons,
        "note": "feasibility + tightness + grounded source => path is globally optimal (LP duality); verified in O(E), no Dijkstra.",
    }
