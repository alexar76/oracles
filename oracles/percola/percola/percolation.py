"""Percolation — network-resilience analysis with a deterministic, replayable proof.

PERCOLA answers a question no per-node reputation score can: not *who* in a network
is trustworthy, but *when the network as a whole loses connectivity*. It treats a
trust/dependency graph as a percolation system and computes the **critical attack
fraction ``f_c``** — the fraction of the highest-leverage nodes an adversary must
remove before the giant connected component collapses (the order parameter
``P_inf`` falls off a cliff). This is the same second-order connectivity phase
transition that governs how a forest fire jumps a firebreak or an outbreak becomes
a pandemic — the canonical physics of a tipping point.

Everything here is exact and replayable — no heuristics, no RNG that the oracle
controls:

1. **Canonicalisation.** The input graph is normalised (sorted, de-duplicated,
   self-loops dropped) and hashed to a ``graph_commitment`` (SHA-256). The whole
   analysis is a pure function of that committed graph.
2. **Targeted attack.** Nodes are removed in a deterministic greedy order — at each
   step the highest-current-degree node, ties broken by lowest index. No randomness,
   so any verifier recomputes the exact same order from the graph alone.
3. **Random attack (baseline).** A seeded Fisher–Yates permutation whose seed is
   ``H(graph_commitment || nonce)`` — committed *before* evaluation, so the oracle
   cannot fish for a flattering order.
4. **Sweep.** For each sampled removal count we rebuild connectivity with a
   union–find (disjoint-set) structure and record the largest component ``P_inf``
   and the second-largest ``S2``. ``f_c`` is read off at the **susceptibility peak**
   (the value of ``f`` that maximises ``S2``) — the textbook observable witness of
   the transition.

A verifier replays the union–find over the exact removal sequence and reproduces
``P_inf(f)`` bit-for-bit, and ``f_c`` to the chosen sampling resolution. The
threshold is **proven by recomputation, not asserted on trust.**
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

# Guards against pathological payloads (the targeted greedy order is O(n^2)).
MAX_NODES = 2000
MAX_EDGES = 20000
MAX_SAMPLES = 200


class DSU:
    """Union–find with union-by-size + path halving."""

    def __init__(self, n: int) -> None:
        self.parent = list(range(n))
        self.size = [1] * n

    def find(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return
        if self.size[ra] < self.size[rb]:
            ra, rb = rb, ra
        self.parent[rb] = ra
        self.size[ra] += self.size[rb]


def canonical_graph(
    nodes: list[Any] | None, edges: list[list[Any]]
) -> tuple[list[str], dict[str, int], list[set[int]], list[tuple[int, int]], str]:
    """Normalise an arbitrary node-labelled graph to a canonical, hashable form.

    Returns ``(labels, index, adjacency, edge_list, commitment)`` where labels are
    the sorted unique node identifiers (as strings), index maps label→position,
    adjacency is a list of neighbour-index sets, edge_list is the sorted unique
    undirected edges as index pairs, and commitment is the SHA-256 of the canonical
    JSON ``{"nodes": [...], "edges": [[i,j],...]}``.
    """
    label_set: set[str] = set(str(x) for x in (nodes or []))
    norm_edges: list[tuple[str, str]] = []
    for e in edges:
        if not isinstance(e, (list, tuple)) or len(e) < 2:
            raise ValueError("each edge must be a [u, v] pair")
        a, b = str(e[0]), str(e[1])
        label_set.add(a)
        label_set.add(b)
        if a == b:
            continue  # drop self-loops — they never affect connectivity
        norm_edges.append((a, b) if a <= b else (b, a))

    labels = sorted(label_set)
    if not labels:
        raise ValueError("graph has no nodes")
    if len(labels) > MAX_NODES:
        raise ValueError(f"too many nodes (max {MAX_NODES})")

    index = {lab: i for i, lab in enumerate(labels)}
    edge_set = sorted({(index[a], index[b]) for a, b in norm_edges})
    if len(edge_set) > MAX_EDGES:
        raise ValueError(f"too many edges (max {MAX_EDGES})")

    adj: list[set[int]] = [set() for _ in labels]
    for a, b in edge_set:
        adj[a].add(b)
        adj[b].add(a)

    canon = {"nodes": labels, "edges": [[a, b] for a, b in edge_set]}
    commitment = hashlib.sha256(
        json.dumps(canon, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()
    return labels, index, adj, edge_set, commitment


def two_largest(active: list[bool], adj: list[set[int]], edge_set: list[tuple[int, int]]) -> tuple[int, int]:
    """Sizes of the largest and second-largest components of the active subgraph."""
    n = len(adj)
    dsu = DSU(n)
    for a, b in edge_set:
        if active[a] and active[b]:
            dsu.union(a, b)
    sizes: dict[int, int] = {}
    for i in range(n):
        if active[i]:
            r = dsu.find(i)
            sizes[r] = sizes.get(r, 0) + 1
    if not sizes:
        return 0, 0
    ordered = sorted(sizes.values(), reverse=True)
    return ordered[0], (ordered[1] if len(ordered) > 1 else 0)


def targeted_order(adj: list[set[int]]) -> list[int]:
    """Deterministic greedy high-leverage removal order.

    Repeatedly remove the node of highest *current* degree (ties → lowest index),
    decrementing its neighbours. Fully deterministic, so it is recomputable by any
    verifier from the canonical graph alone.
    """
    n = len(adj)
    removed = [False] * n
    deg = [len(adj[i]) for i in range(n)]
    order: list[int] = []
    for _ in range(n):
        best, best_deg = -1, -1
        for u in range(n):
            if not removed[u] and deg[u] > best_deg:
                best_deg, best = deg[u], u
        if best < 0:
            break
        removed[best] = True
        order.append(best)
        for v in adj[best]:
            if not removed[v]:
                deg[v] -= 1
    return order


def seed_int(commitment: str, nonce: str) -> int:
    """64-bit seed bound to the committed graph and a nonce (commit-reveal)."""
    h = hashlib.sha256(f"{commitment}|{nonce}".encode()).digest()
    return int.from_bytes(h[:8], "big")


def seeded_order(n: int, seed: int) -> list[int]:
    """Deterministic Fisher–Yates permutation from a 64-bit seed (splitmix64-style)."""
    arr = list(range(n))
    state = seed & 0xFFFFFFFFFFFFFFFF
    for i in range(n - 1, 0, -1):
        state = (state + 0x9E3779B97F4A7C15) & 0xFFFFFFFFFFFFFFFF
        z = state
        z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & 0xFFFFFFFFFFFFFFFF
        z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & 0xFFFFFFFFFFFFFFFF
        z ^= z >> 31
        j = z % (i + 1)
        arr[i], arr[j] = arr[j], arr[i]
    return arr


def sample_ks(n: int, samples: int) -> list[int]:
    """Removal counts to sample, spanning k = 0 … n at the requested resolution."""
    samples = max(2, min(int(samples), MAX_SAMPLES, n))
    return sorted({round(i * n / samples) for i in range(samples + 1)})


def sweep(order: list[int], adj: list[set[int]], edge_set: list[tuple[int, int]], n: int, samples: int) -> tuple[list[dict[str, float]], float]:
    """Collapse curve + critical fraction for one removal order.

    Returns ``(curve, f_c)`` where curve is a list of
    ``{"f", "p_inf", "s2", "removed"}`` points and ``f_c`` is the ``f`` at the
    susceptibility (second-cluster) peak.
    """
    curve: list[dict[str, float]] = []
    for k in sample_ks(n, samples):
        active = [True] * n
        for i in range(k):
            active[order[i]] = False
        p1, p2 = two_largest(active, adj, edge_set)
        curve.append(
            {"f": round(k / n, 4), "p_inf": round(p1 / n, 4), "s2": round(p2 / n, 4), "removed": k}
        )
    # f_c = the f that maximises the second-largest cluster (susceptibility peak).
    peak = max(curve, key=lambda c: (c["s2"], -c["f"]))
    return curve, peak["f"]


def robustness(curve: list[dict[str, float]]) -> float:
    """Trapezoidal area under P_inf(f) over f∈[0,1] — a single 0…1 resilience scalar."""
    if len(curve) < 2:
        return 0.0
    area = 0.0
    for i in range(1, len(curve)):
        df = curve[i]["f"] - curve[i - 1]["f"]
        area += 0.5 * (curve[i]["p_inf"] + curve[i - 1]["p_inf"]) * df
    return round(area, 4)


def order_hash(order: list[int], labels: list[str]) -> str:
    """SHA-256 of the removal order expressed in canonical node labels."""
    payload = json.dumps([labels[i] for i in order], separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode()).hexdigest()


def analyze(
    nodes: list[Any] | None,
    edges: list[list[Any]],
    samples: int = 50,
    nonce: str = "0",
    attack: str = "both",
) -> dict[str, Any]:
    """Full PERCOLA analysis — the ``percola.threshold@v1`` handler core."""
    labels, _index, adj, edge_set, commitment = canonical_graph(nodes, edges)
    n = len(labels)
    attack = attack if attack in ("targeted", "random", "both") else "both"

    out: dict[str, Any] = {
        "n": n,
        "m": len(edge_set),
        "graph_commitment": commitment,
        "samples": max(2, min(int(samples), MAX_SAMPLES, n)),
    }

    if attack in ("targeted", "both"):
        t_order = targeted_order(adj)
        t_curve, t_fc = sweep(t_order, adj, edge_set, n, samples)
        keystone_count = max(1, min(n, -(-int(round(t_fc * n)))))  # ceil(f_c * n)
        out["robustness"] = robustness(t_curve)
        out["targeted"] = {
            "f_c": t_fc,
            "curve": t_curve,
            "keystones": [labels[i] for i in t_order[:keystone_count]],
            "order_hash": order_hash(t_order, labels),
            "note": "deterministic greedy max-degree order; recomputable from the graph alone.",
        }

    if attack in ("random", "both"):
        seed = seed_int(commitment, str(nonce))
        r_order = seeded_order(n, seed)
        r_curve, r_fc = sweep(r_order, adj, edge_set, n, samples)
        out["random"] = {
            "f_c": r_fc,
            "curve": r_curve,
            "nonce": str(nonce),
            "seed": format(seed, "016x"),
            "order_hash": order_hash(r_order, labels),
            "note": "Fisher-Yates from seed = H(graph_commitment || nonce); recomputable.",
        }

    return out


def verify(
    nodes: list[Any] | None,
    edges: list[list[Any]],
    attack: str = "targeted",
    f_c: float | None = None,
    nonce: str = "0",
    seed: str | None = None,
    samples: int = 50,
) -> dict[str, Any]:
    """Trustless re-computation — the ``percola.verify@v1`` handler core.

    Re-derives the canonical graph, reconstructs the (deterministic) removal order,
    replays the sweep, and checks the claimed ``f_c`` against the recomputed value.
    """
    labels, _index, adj, edge_set, commitment = canonical_graph(nodes, edges)
    n = len(labels)

    if attack == "random":
        used_seed = int(seed, 16) if seed else seed_int(commitment, str(nonce))
        order = seeded_order(n, used_seed)
        seed_repr: str | None = format(used_seed, "016x")
    else:
        attack = "targeted"
        order = targeted_order(adj)
        seed_repr = None

    _curve, recomputed_fc = sweep(order, adj, edge_set, n, samples)
    valid = f_c is not None and abs(float(f_c) - recomputed_fc) < 1e-9

    return {
        "valid": bool(valid),
        "attack": attack,
        "graph_commitment": commitment,
        "recomputed_f_c": recomputed_fc,
        "claimed_f_c": (None if f_c is None else round(float(f_c), 4)),
        "order_hash": order_hash(order, labels),
        "seed": seed_repr,
    }
