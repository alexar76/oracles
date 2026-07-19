"""ABLATION — systemic cascade-risk via the abelian sandpile (self-organized criticality).

ABLATION answers a question no per-node default-probability can: not *who* is likely to
fail, but *how big the resulting avalanche is when they do* — the full heavy-tailed
distribution of cascade **magnitudes** that a driven, dissipative network produces under
load. It treats an exposure graph (who-owes-whom / who-depends-on-whom) as a
**Bak–Tang–Wiesenfeld abelian sandpile**: each node accumulates "stress" (grains); when a
node's load reaches its threshold it **topples**, shedding grains to its out-neighbours,
which can push *them* over threshold — a chain reaction, an **avalanche**. In the critical
state these avalanche sizes obey a power law ``P(s) ~ s^(-tau)``: most are tiny, but a few
are system-spanning catastrophes. ABLATION measures that exponent, the tail risk, and the
nodes that most often ignite the big ones.

Everything here is exact and replayable — no heuristics, no RNG the oracle controls:

1. **Canonicalisation.** The exposure graph, the per-node capacities (toppling thresholds)
   and the dissipation set (sink nodes) are normalised and hashed to a
   ``config_commitment`` (SHA-256). The whole analysis is a pure function of that commit.
2. **Committed drive schedule.** Grains are dropped on a deterministic pseudo-random
   sequence of nodes whose seed is ``H(config_commitment || nonce)`` — committed *before*
   evaluation, so the oracle cannot fish for a flattering avalanche series.
3. **Stabilisation by toppling.** After each drop the configuration is relaxed with a
   topple queue until every node is below threshold. The **abelian property** (a theorem of
   Dhar) guarantees the final stable configuration *and the per-site topple counts* are
   **independent of the order** in which unstable sites are relaxed. So a verifier may
   replay the relaxation in any order and reproduce the topple counts and the avalanche
   sizes **bit-for-bit**.
4. **Statistics.** From the recorded avalanche-size series ABLATION derives the size
   distribution, the **MLE power-law exponent ``tau``** (discrete Hill/Clauset estimator),
   a **Kolmogorov–Smirnov** goodness-of-fit against the fitted law, the mean avalanche
   size, the **95% / 99% tail risk** (VaR and CVaR / expected-shortfall), and the **trigger
   nodes** that most often start large cascades. Every statistic is a deterministic
   function of the committed run.

A verifier replays the driven-dissipative sandpile over the committed schedule and
reproduces the total topple count and ``tau``. The systemic-risk premium is **proven by
recomputation, not asserted on trust.**
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any

# Guards against pathological payloads. Stabilisation is bounded because every grain
# dropped is eventually dissipated at a sink, so total topples <= O(grains * diameter);
# the caps below keep one call well under a few hundred ms.
MAX_NODES = 4000
MAX_EDGES = 40000
MAX_GRAINS = 20000
MAX_TOPPLES = 5_000_000  # hard ceiling on relaxation work per run (safety net)


def _to_label(x: Any) -> str:
    return str(x)


def canonical_config(
    edges: list[list[Any]],
    capacities: dict[Any, Any] | None = None,
    thresholds: dict[Any, Any] | None = None,
    nodes: list[Any] | None = None,
    sinks: list[Any] | None = None,
    dissipation: int = 1,
) -> dict[str, Any]:
    """Normalise an arbitrary exposure graph + load field to a canonical, hashable form.

    The exposure graph is **directed**: edge ``[u, v]`` means stress flows from ``u`` to
    ``v`` (u depends on / owes v, so u's distress lands on v). A toppling node sheds one
    grain down each of its out-edges **plus ``dissipation`` grains to the open boundary**
    (the BTW open-boundary rule), so its threshold (capacity) defaults to
    ``out_degree + dissipation``. ``dissipation`` is the system's leak rate: ``>=1``
    guarantees criticality and termination on *any* graph (energy must leave a driven SOC
    system); set ``0`` for a perfectly conservative network (then dissipation happens only
    at explicit sinks / dead-ends). An explicit per-node capacity overrides the default.
    ``thresholds`` is an accepted alias for ``capacities``.

    Returns a dict with: ``labels`` (sorted unique node ids as strings), ``index``
    (label→position), ``out`` (list of out-neighbour-index lists, sorted), ``capacity``
    (per-index toppling threshold, >=1), ``is_sink`` (per-index bool — sinks dissipate
    grains and never topple), ``leaky`` (per-index bool — trapped nodes that leak to the
    boundary), ``dissipation``, ``n``, ``m``, and ``commitment`` (SHA-256 of the canonical
    JSON).
    """
    cap_in = {_to_label(k): v for k, v in (capacities or thresholds or {}).items()}
    sink_in = {_to_label(s) for s in (sinks or [])}
    dissipation = max(0, int(dissipation))

    label_set: set[str] = set(_to_label(x) for x in (nodes or []))
    label_set |= set(cap_in.keys())
    label_set |= sink_in
    norm_edges: list[tuple[str, str]] = []
    for e in edges:
        if not isinstance(e, (list, tuple)) or len(e) < 2:
            raise ValueError("each edge must be a [u, v] pair (directed: stress flows u->v)")
        a, b = _to_label(e[0]), _to_label(e[1])
        label_set.add(a)
        label_set.add(b)
        if a == b:
            continue  # drop self-loops — a grain shed to self is a no-op
        norm_edges.append((a, b))

    labels = sorted(label_set)
    if not labels:
        raise ValueError("graph has no nodes")
    if len(labels) > MAX_NODES:
        raise ValueError(f"too many nodes (max {MAX_NODES})")

    index = {lab: i for i, lab in enumerate(labels)}

    # De-duplicate directed edges, then build sorted out-adjacency.
    edge_set = sorted({(index[a], index[b]) for a, b in norm_edges})
    if len(edge_set) > MAX_EDGES:
        raise ValueError(f"too many edges (max {MAX_EDGES})")

    out: list[list[int]] = [[] for _ in labels]
    for a, b in edge_set:
        out[a].append(b)

    is_sink = [labels[i] in sink_in for i in range(len(labels))]

    # --- Guarantee dissipation (so stabilisation always terminates) ---------------
    # An abelian sandpile relaxes to a stable state iff every node can reach a
    # dissipative boundary (Dhar). A node with no out-edges already dissipates into the
    # void. A node trapped in a strongly-connected component with no path to any sink /
    # boundary would topple forever — unphysical. We treat every such trapped node as a
    # *leaky boundary* node (`leaky[i] = True`): each unit topple loses one grain to the
    # boundary, exactly the open-boundary treatment of BTW. This is a fixed, per-node,
    # order-independent rule, so it preserves the abelian property and is folded into the
    # commitment. The result: every input stabilises; no caller can stall the service.
    n_nodes = len(labels)
    if dissipation >= 1:
        # Every non-sink topple already leaks to the boundary, so the pile is globally
        # dissipative and always stabilises — no trapped nodes possible.
        leaky = [False] * n_nodes
    else:
        # Perfectly conservative network (dissipation == 0): dissipation happens only at
        # explicit sinks and dead-ends. A node trapped in a sink-less SCC would topple
        # forever, so mark it a *leaky boundary* node (Dhar open boundary). Computed by
        # reverse-reachability from the dissipative frontier — deterministic, so a verifier
        # reconstructs the identical set and it goes into the commitment.
        can_dissipate = [False] * n_nodes
        frontier: list[int] = []
        for i in range(n_nodes):
            if is_sink[i] or len(out[i]) == 0:
                can_dissipate[i] = True
                frontier.append(i)
        rev: list[list[int]] = [[] for _ in labels]
        for a, b in edge_set:
            rev[b].append(a)
        head = 0
        while head < len(frontier):
            node = frontier[head]
            head += 1
            for p in rev[node]:
                if not can_dissipate[p]:
                    can_dissipate[p] = True
                    frontier.append(p)
        leaky = [(not can_dissipate[i]) and (not is_sink[i]) for i in range(n_nodes)]

    capacity: list[int] = []
    for i, lab in enumerate(labels):
        if lab in cap_in:
            c = int(cap_in[lab])
            if c < 1:
                raise ValueError(f"capacity for node {lab!r} must be >= 1")
            capacity.append(c)
        else:
            # Open-boundary BTW threshold = out-degree + dissipation: a topple sheds one
            # grain per out-edge and `dissipation` to the boundary. Isolated nodes get >=1.
            capacity.append(max(1, len(out[i]) + dissipation))

    # Canonical form for the commitment: labels, directed edges, capacities, sinks, and the
    # derived leaky (trapped-boundary) set — all deterministic functions of the input, so a
    # verifier reconstructs an identical commitment and dissipation rule.
    canon = {
        "nodes": labels,
        "edges": [[a, b] for a, b in edge_set],
        "capacity": capacity,
        "sinks": sorted(i for i in range(len(labels)) if is_sink[i]),
        "leaky": sorted(i for i in range(len(labels)) if leaky[i]),
        "dissipation": dissipation,
    }
    commitment = hashlib.sha256(
        json.dumps(canon, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()

    return {
        "labels": labels,
        "index": index,
        "out": out,
        "capacity": capacity,
        "is_sink": is_sink,
        "leaky": leaky,
        "dissipation": dissipation,
        "n": len(labels),
        "m": len(edge_set),
        "commitment": commitment,
    }


def seed_int(commitment: str, nonce: str) -> int:
    """64-bit seed bound to the committed config and a nonce (commit-reveal)."""
    h = hashlib.sha256(f"{commitment}|{nonce}".encode()).digest()
    return int.from_bytes(h[:8], "big")


class _SplitMix64:
    """Deterministic splitmix64 stream — the only randomness, fully reproducible."""

    __slots__ = ("state",)

    def __init__(self, seed: int) -> None:
        self.state = seed & 0xFFFFFFFFFFFFFFFF

    def next(self) -> int:
        self.state = (self.state + 0x9E3779B97F4A7C15) & 0xFFFFFFFFFFFFFFFF
        z = self.state
        z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & 0xFFFFFFFFFFFFFFFF
        z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & 0xFFFFFFFFFFFFFFFF
        z ^= z >> 31
        return z & 0xFFFFFFFFFFFFFFFF

    def below(self, n: int) -> int:
        return self.next() % n


def _stabilise(
    load: list[int],
    out: list[list[int]],
    capacity: list[int],
    is_sink: list[bool],
    leaky: list[bool],
    seeded_unstable: list[int],
    topples: list[int],
    topple_budget: list[int],
) -> int:
    """Relax the configuration until stable; return the avalanche size (# of topples).

    A site ``i`` is unstable when ``load[i] >= capacity[i]``. Toppling sheds exactly
    ``capacity[i]`` grains: one along each of the first ``deg`` out-edges (round-robin if
    ``capacity > deg`` — but the canonical threshold is the out-degree, so by default each
    out-neighbour receives exactly one). Sink nodes never topple — they dissipate grains,
    which is what makes the dynamics *driven-dissipative* and the avalanches finite.
    ``leaky`` nodes (trapped in a sink-less SCC) lose all shed grains to the open boundary,
    guaranteeing termination on any graph.

    The **abelian property** means the returned topple count is independent of the order in
    which we pop unstable sites — so this is the canonical, verifier-reproducible relaxation.
    """
    queue = list(seeded_unstable)
    in_q = [False] * len(load)
    for i in queue:
        in_q[i] = True
    size = 0
    head = 0
    while head < len(queue):
        i = queue[head]
        head += 1
        in_q[i] = False
        if is_sink[i] or load[i] < capacity[i]:
            continue
        deg = len(out[i])
        thr = capacity[i]
        # Topple as many times as the node is over threshold (drains multiples in one step;
        # still abelian — each unit topple sheds `thr` grains over the out-edges).
        n_topple = load[i] // thr
        if n_topple <= 0:
            continue
        size += n_topple
        topples[i] += n_topple
        topple_budget[0] -= n_topple
        if topple_budget[0] < 0:
            raise ValueError("relaxation exceeded MAX_TOPPLES — input too heavy")
        load[i] -= n_topple * thr
        if deg == 0 or leaky[i]:
            # No out-edges, or trapped node: shed grains to the open boundary (dissipation).
            continue
        # Distribute n_topple grains down each of the `deg` channels (BTW: one per channel
        # per unit topple). Capacity may differ from deg if the caller set it explicitly;
        # we shed one grain per out-edge per unit topple, which conserves the BTW rule for
        # capacity == deg and degrades gracefully otherwise.
        for v in out[i]:
            load[v] += n_topple
            if not is_sink[v] and load[v] >= capacity[v] and not in_q[v]:
                in_q[v] = True
                queue.append(v)
    return size


def run_sandpile(
    cfg: dict[str, Any],
    grains: int,
    nonce: str,
) -> dict[str, Any]:
    """Drive the dissipative sandpile and record the avalanche-size series.

    Drops ``grains`` grains one at a time on a committed pseudo-random sequence of
    non-sink nodes; after each drop the pile is stabilised and the avalanche size (number
    of topples triggered) recorded. Returns the raw series, per-node topple counts, per-node
    trigger-and-cascade tallies, and the committed seed. Pure function of the committed
    config + nonce.
    """
    n = cfg["n"]
    out = cfg["out"]
    capacity = cfg["capacity"]
    is_sink = cfg["is_sink"]
    leaky = cfg["leaky"]
    commitment = cfg["commitment"]

    grains = max(1, min(int(grains), MAX_GRAINS))
    seed = seed_int(commitment, str(nonce))
    rng = _SplitMix64(seed)

    drivable = [i for i in range(n) if not is_sink[i]]
    if not drivable:
        raise ValueError("every node is a sink — nothing to drive")

    load = [0] * n
    topples = [0] * n           # total times each node toppled across the whole run
    trigger_count = [0] * n     # times each node was the seed of an avalanche
    trigger_mass = [0] * n      # total cascade size summed over avalanches each node seeded
    big_trigger = [0] * n       # times each node seeded a 'large' avalanche (>= threshold)

    sizes: list[int] = []
    topple_budget = [MAX_TOPPLES]

    for _ in range(grains):
        site = drivable[rng.below(len(drivable))]
        load[site] += 1
        avalanche = 0
        if not is_sink[site] and load[site] >= capacity[site]:
            avalanche = _stabilise(
                load, out, capacity, is_sink, leaky, [site], topples, topple_budget
            )
        sizes.append(avalanche)
        if avalanche > 0:
            trigger_count[site] += 1
            trigger_mass[site] += avalanche

    topple_total = sum(topples)

    # 'Large' avalanche threshold = 90th percentile of the non-zero sizes (the heavy tail).
    nonzero = sorted(s for s in sizes if s > 0)
    if nonzero:
        big_cut = nonzero[int(0.9 * (len(nonzero) - 1))]
    else:
        big_cut = 0
    # Re-attribute big triggers (cheap second pass over the recorded series).
    # We recompute which drop seeded which avalanche deterministically by replaying the
    # site sequence — but we already know order, so attribute from the recorded mapping.
    # (Reconstruct site sequence to map big avalanches back to their trigger node.)
    rng2 = _SplitMix64(seed)
    for k in range(grains):
        site = drivable[rng2.below(len(drivable))]
        if sizes[k] >= big_cut and sizes[k] > 0:
            big_trigger[site] += 1

    return {
        "n": n,
        "m": cfg["m"],
        "grains": grains,
        "config_commitment": commitment,
        "seed": format(seed, "016x"),
        "nonce": str(nonce),
        "sizes": sizes,
        "topples": topples,
        "topple_total": topple_total,
        "trigger_count": trigger_count,
        "trigger_mass": trigger_mass,
        "big_trigger": big_trigger,
        "big_cut": big_cut,
    }


# ---------------------------------------------------------------------------
# Power-law statistics on the avalanche-size distribution.
# ---------------------------------------------------------------------------

def size_distribution(sizes: list[int]) -> dict[str, int]:
    """Histogram of *non-zero* avalanche sizes: {size_as_str: count}."""
    hist: dict[int, int] = {}
    for s in sizes:
        if s > 0:
            hist[s] = hist.get(s, 0) + 1
    return {str(k): hist[k] for k in sorted(hist)}


def mle_tau(sizes: list[int], s_min: int = 1) -> float:
    """Discrete MLE power-law exponent tau (Clauset-Newman-Watts approximation).

    For ``P(s) ~ s^(-tau)`` on integers ``s >= s_min``, the maximum-likelihood estimator is

        tau = 1 + N / sum_i ln( s_i / (s_min - 0.5) ).

    Deterministic and closed-form; returns 0.0 when there is no tail to fit.
    """
    data = [s for s in sizes if s >= s_min and s > 0]
    n = len(data)
    if n < 2:
        return 0.0
    denom = 0.0
    base = s_min - 0.5
    if base <= 0:
        base = 0.5
    for s in data:
        denom += math.log(s / base)
    if denom <= 0:
        return 0.0
    return 1.0 + n / denom


def ks_statistic(sizes: list[int], tau: float, s_min: int = 1) -> float:
    """Kolmogorov–Smirnov distance between the empirical CDF and the fitted power law.

    Compares the empirical CDF of ``s >= s_min`` to the discrete power-law CDF with the
    given exponent ``tau``. Smaller = better fit; deterministic.
    """
    data = sorted(s for s in sizes if s >= s_min and s > 0)
    n = len(data)
    if n < 2 or tau <= 1.0:
        return 1.0
    s_max = data[-1]
    # Discrete zeta-like normalisation over the observed support [s_min, s_max].
    weights = [k ** (-tau) for k in range(s_min, s_max + 1)]
    total = sum(weights)
    if total <= 0:
        return 1.0
    # Model CDF at each integer value.
    cdf_model: dict[int, float] = {}
    acc = 0.0
    for idx, k in enumerate(range(s_min, s_max + 1)):
        acc += weights[idx]
        cdf_model[k] = acc / total
    # Empirical CDF and the KS sup-distance.
    d_max = 0.0
    for rank, s in enumerate(data, start=1):
        emp = rank / n
        mdl = cdf_model.get(s, 1.0)
        d_max = max(d_max, abs(emp - mdl), abs((rank - 1) / n - mdl))
    return d_max


def tail_risk(sizes: list[int], quantile: float) -> dict[str, float]:
    """VaR (the quantile) and CVaR / expected-shortfall (mean beyond it) of avalanche size.

    Computed over the full size series (including zero-avalanche drops), so it answers the
    real question: *given a random shock, how big is the cascade at the q-th percentile, and
    how bad is the average catastrophe past it?*
    """
    data = sorted(sizes)
    n = len(data)
    if n == 0:
        return {"var": 0.0, "cvar": 0.0, "quantile": quantile}
    q = min(max(quantile, 0.0), 1.0)
    # VaR index (nearest-rank, 1-based).
    idx = max(0, min(n - 1, int(math.ceil(q * n)) - 1))
    var = float(data[idx])
    tail = data[idx:]
    cvar = float(sum(tail) / len(tail)) if tail else var
    return {"var": round(var, 4), "cvar": round(cvar, 4), "quantile": round(q, 4)}


def _round_curve(hist: dict[str, int]) -> list[dict[str, int]]:
    """Distribution as a sorted list of {size, count} for log-log plotting."""
    return [{"size": int(k), "count": v} for k, v in hist.items()]


def _top_triggers(
    labels: list[str],
    trigger_count: list[int],
    trigger_mass: list[int],
    big_trigger: list[int],
    k: int = 8,
) -> list[dict[str, Any]]:
    """The nodes that most often ignite *large* cascades (ranked by big-trigger count,
    then total cascade mass)."""
    n = len(labels)
    ranked = sorted(
        range(n),
        key=lambda i: (big_trigger[i], trigger_mass[i], trigger_count[i], -i),
        reverse=True,
    )
    out: list[dict[str, Any]] = []
    for i in ranked[:k]:
        if trigger_count[i] == 0:
            continue
        out.append(
            {
                "node": labels[i],
                "big_cascades": big_trigger[i],
                "avalanches_seeded": trigger_count[i],
                "total_cascade_mass": trigger_mass[i],
            }
        )
    return out


def cascade(
    edges: list[list[Any]],
    capacities: dict[Any, Any] | None = None,
    thresholds: dict[Any, Any] | None = None,
    nodes: list[Any] | None = None,
    sinks: list[Any] | None = None,
    grains: int = 4000,
    nonce: str = "0",
    s_min: int = 1,
    dissipation: int = 1,
) -> dict[str, Any]:
    """Full ABLATION analysis — the ``ablation.cascade@v1`` handler core."""
    cfg = canonical_config(edges, capacities, thresholds, nodes, sinks, dissipation)
    run = run_sandpile(cfg, grains, nonce)
    sizes = run["sizes"]
    labels = cfg["labels"]

    hist = size_distribution(sizes)
    s_min = max(1, int(s_min))
    tau = mle_tau(sizes, s_min)
    ks = ks_statistic(sizes, tau, s_min)

    nonzero = [s for s in sizes if s > 0]
    mean_avalanche = (sum(nonzero) / len(nonzero)) if nonzero else 0.0
    max_avalanche = max(sizes) if sizes else 0
    n_avalanches = len(nonzero)

    var95 = tail_risk(sizes, 0.95)
    var99 = tail_risk(sizes, 0.99)

    triggers = _top_triggers(
        labels, run["trigger_count"], run["trigger_mass"], run["big_trigger"]
    )

    return {
        "n": cfg["n"],
        "m": cfg["m"],
        "grains": run["grains"],
        "config_commitment": cfg["commitment"],
        "seed": run["seed"],
        "nonce": run["nonce"],
        "dissipation": cfg["dissipation"],
        "topple_total": run["topple_total"],
        "n_avalanches": n_avalanches,
        "distribution": _round_curve(hist),
        "tau": round(tau, 4),
        "ks": round(ks, 4),
        "s_min": s_min,
        "mean_avalanche": round(mean_avalanche, 4),
        "max_avalanche": max_avalanche,
        "var95": var95,
        "cvar95": var95["cvar"],
        "var99": var99,
        "cvar99": var99["cvar"],
        "triggers": triggers,
        "note": (
            "Abelian sandpile (BTW SOC). Avalanche sizes are order-independent topple "
            "counts over a committed drive schedule; small tau / heavy tail = high "
            "systemic contagion risk. Replay with ablation.verify@v1."
        ),
    }


def verify(
    edges: list[list[Any]],
    capacities: dict[Any, Any] | None = None,
    thresholds: dict[Any, Any] | None = None,
    nodes: list[Any] | None = None,
    sinks: list[Any] | None = None,
    grains: int = 4000,
    nonce: str = "0",
    seed: str | None = None,
    claimed_tau: float | None = None,
    claimed_topple_total: int | None = None,
    s_min: int = 1,
    dissipation: int = 1,
    tol: float = 1e-4,
) -> dict[str, Any]:
    """Trustless re-computation — the ``ablation.verify@v1`` handler core.

    Re-derives the canonical config, replays the driven-dissipative sandpile over the
    committed schedule (re-deriving the seed from ``H(commitment || nonce)`` unless a seed
    is supplied), recomputes the order-independent topple total and the power-law exponent,
    and checks them against the claimed values. The abelian theorem guarantees the topple
    counts are reproduced exactly regardless of relaxation order.
    """
    cfg = canonical_config(edges, capacities, thresholds, nodes, sinks, dissipation)

    # If a raw seed is supplied, replay from it directly; else derive from the commitment.
    if seed is not None:
        seed_int_val = int(str(seed), 16)
        used_nonce = None
    else:
        used_nonce = str(nonce)
        seed_int_val = seed_int(cfg["commitment"], used_nonce)

    # Replay sandpile with the resolved seed by faking a nonce that produces it: we replay
    # run_sandpile directly so the seed path is identical — derive via a thin wrapper.
    grains_c = max(1, min(int(grains), MAX_GRAINS))
    rng = _SplitMix64(seed_int_val)
    n = cfg["n"]
    out, capacity, is_sink, leaky = cfg["out"], cfg["capacity"], cfg["is_sink"], cfg["leaky"]
    drivable = [i for i in range(n) if not is_sink[i]]
    if not drivable:
        raise ValueError("every node is a sink — nothing to drive")
    load = [0] * n
    topples = [0] * n
    topple_budget = [MAX_TOPPLES]
    sizes: list[int] = []
    for _ in range(grains_c):
        site = drivable[rng.below(len(drivable))]
        load[site] += 1
        av = 0
        if not is_sink[site] and load[site] >= capacity[site]:
            av = _stabilise(load, out, capacity, is_sink, leaky, [site], topples, topple_budget)
        sizes.append(av)

    s_min = max(1, int(s_min))
    recomputed_topple_total = sum(topples)
    recomputed_tau = round(mle_tau(sizes, s_min), 4)

    valid = True
    checked = False
    if claimed_topple_total is not None:
        checked = True
        valid = valid and (int(claimed_topple_total) == recomputed_topple_total)
    if claimed_tau is not None:
        checked = True
        valid = valid and (abs(float(claimed_tau) - recomputed_tau) <= tol)
    if not checked:
        valid = False  # nothing claimed → nothing proven

    return {
        "valid": bool(valid),
        "config_commitment": cfg["commitment"],
        "seed": format(seed_int_val, "016x"),
        "nonce": used_nonce,
        "recomputed_topple_total": recomputed_topple_total,
        "recomputed_tau": recomputed_tau,
        "claimed_topple_total": (None if claimed_topple_total is None else int(claimed_topple_total)),
        "claimed_tau": (None if claimed_tau is None else round(float(claimed_tau), 4)),
        "note": (
            "Abelian sandpile relaxation is order-independent (Dhar's theorem): the topple "
            "total and tau are reproduced bit-for-bit regardless of relaxation order."
        ),
    }
