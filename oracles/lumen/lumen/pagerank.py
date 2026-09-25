"""EigenTrust / PageRank reputation over a directed weighted trust graph.

Reputation is the *stationary distribution* of a damped random walk on who-trusts-whom.
Given directed weighted edges ``i -> j`` (agent ``i`` extends ``weight`` units of trust
to agent ``j``), we build a **column-stochastic** transition matrix ``M`` where each
source column ``i`` is normalized to a probability distribution over whom ``i`` trusts.
So ``M[j, i]`` is the probability that a walker currently at ``i`` steps to ``j``. The
PageRank vector is the
dominant eigenvector of the Google matrix::

    G = d · M + (1 - d) · (1/n) · 1·1ᵀ

with damping ``d`` (default 0.85). A walker follows a trust edge with probability ``d``
and teleports to a uniformly random node with probability ``1 - d``. We solve for the
fixed point ``r = G·r`` by **power iteration** (repeatedly applying ``G`` to a uniform
seed until it stops moving). The result is the dominant eigenvector — Perron–Frobenius
guarantees it is unique, strictly positive, and that power iteration converges because
``G`` is a positive stochastic matrix (spectral gap ``1 - d``).

This is the real EigenTrust kernel used for sybil-resistant reputation in P2P / agent
economies: trust flows transitively, nodes trusted *by trusted nodes* score highest,
and the ``(1 - d)`` teleport keeps the walk ergodic so isolated cliques cannot trap it.

Key correctness properties (all asserted by the tests):
  * scores form a probability distribution: non-negative, sum to 1 (± 1e-6);
  * the most-trusted node on a hand-built graph gets the top score;
  * power iteration converges — the L1 delta between iterates falls below ``tol``;
  * **dangling nodes** (no outgoing trust) are handled by uniform teleport, so they do
    not leak rank mass (the matrix stays exactly column-stochastic).
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from typing import Any

import numpy as np

DEFAULT_DAMPING = 0.85
DEFAULT_TOL = 1e-10
DEFAULT_MAX_ITER = 1000
MAX_NODES = 100_000
#: Ceiling on the dense transition matrix, in bytes. MAX_NODES bounds the node COUNT, but
#: the matrix is n x n float64 -- at n = MAX_NODES that is 8e10 bytes, so a 60-byte request
#: ({"nodes": 100000, "edges": []}) asked for an 80 GB allocation and OOM-killed the whole
#: oracle-family process. The dangling-column pass then touches every one of those bytes,
#: so it is not even lazily mapped. Override with LUMEN_MAX_MATRIX_BYTES.
MAX_MATRIX_BYTES = max(1_000_000, int(os.environ.get("LUMEN_MAX_MATRIX_BYTES", 256 * 1024 * 1024)))


def build_transition_matrix(nodes: int, edges: list[list[float]]) -> np.ndarray:
    """Build the column-stochastic transition matrix ``M`` from trust edges.

    ``edges`` is a list of ``[i, j, w]`` meaning node ``i`` trusts node ``j`` with
    positive weight ``w``. Each source column ``i`` is normalized to sum to 1 (a
    probability distribution over whom ``i`` trusts). A source with no outgoing trust
    (a **dangling node**) is replaced by the uniform column ``1/n`` so the walker
    teleports rather than vanishing — this keeps every column summing to exactly 1.

    Returns an ``(n, n)`` matrix ``M`` with ``M[j, i] = P(step to j | at i)``.
    """
    if nodes <= 0:
        raise ValueError("nodes must be a positive integer")
    n = int(nodes)
    needed = n * n * 8
    if needed > MAX_MATRIX_BYTES:
        max_n = int(math.isqrt(MAX_MATRIX_BYTES // 8))
        raise ValueError(
            f"nodes={n} needs a {needed} byte dense transition matrix, over the "
            f"{MAX_MATRIX_BYTES} byte ceiling (max nodes here: {max_n}). "
            "Raise LUMEN_MAX_MATRIX_BYTES only if the host really has the memory."
        )
    M = np.zeros((n, n), dtype=np.float64)

    for edge in edges:
        if len(edge) != 3:
            raise ValueError(f"each edge must be [i, j, w]; got {edge!r}")
        i, j, w = int(edge[0]), int(edge[1]), float(edge[2])
        if not (0 <= i < n and 0 <= j < n):
            raise ValueError(f"edge endpoint out of range for n={n}: {edge!r}")
        if w < 0:
            raise ValueError(f"trust weight must be non-negative: {edge!r}")
        # M[j, i]: trust flowing FROM i (the column/source) TO j (the row/target).
        M[j, i] += w

    col_sums = M.sum(axis=0)
    for col in range(n):
        if col_sums[col] > 0:
            M[:, col] /= col_sums[col]
        else:
            # Dangling node: no outgoing trust -> uniform teleport (column-stochastic).
            M[:, col] = 1.0 / n
    return M


def graph_commitment(nodes: int, edges: list[list[float]]) -> str:
    """Deterministic, order-independent commitment to the canonical trust graph.

    Parallel edges between the same ``(i, j)`` pair are aggregated (weights summed with
    :func:`math.fsum`, whose result is correctly rounded and independent of input order),
    exactly mirroring PageRank's own ``M[j, i] += w`` semantics. The aggregated edges are
    then serialized in sorted, canonical form and hashed with SHA-256.

    The result is ``"sha256:<hexdigest>"``. Two edge lists produce the same commitment iff
    they describe the same weighted graph, so a prover can publish a commitment up front
    and a verifier can later confirm that the edges it re-derives scores over are the ones
    that were committed to — the graph cannot be swapped for a more favorable one after the
    fact. The same input validation as :func:`build_transition_matrix` is enforced, so a
    malformed graph is rejected rather than silently committed.
    """
    n = int(nodes)
    if n <= 0:
        raise ValueError("nodes must be a positive integer")
    buckets: dict[tuple[int, int], list[float]] = {}
    for edge in edges:
        if len(edge) != 3:
            raise ValueError(f"each edge must be [i, j, w]; got {edge!r}")
        i, j, w = int(edge[0]), int(edge[1]), float(edge[2])
        if not (0 <= i < n and 0 <= j < n):
            raise ValueError(f"edge endpoint out of range for n={n}: {edge!r}")
        if w < 0:
            raise ValueError(f"trust weight must be non-negative: {edge!r}")
        buckets.setdefault((i, j), []).append(w)
    # repr(float) round-trips exactly, so the canonical form is reproducible bit-for-bit.
    canonical = [n, [[i, j, repr(math.fsum(ws))] for (i, j), ws in sorted(buckets.items())]]
    payload = json.dumps(canonical, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def pagerank(
    nodes: int,
    edges: list[list[float]],
    damping: float = DEFAULT_DAMPING,
    tol: float = DEFAULT_TOL,
    max_iter: int = DEFAULT_MAX_ITER,
) -> dict[str, Any]:
    """Compute the PageRank / EigenTrust reputation vector via power iteration.

    Iterates ``r_{k+1} = d · M · r_k + (1 - d) / n`` (the rank-one teleport term folds
    into a constant because ``r_k`` sums to 1) until ``‖r_{k+1} - r_k‖₁ < tol`` or
    ``max_iter`` is reached. Returns normalized scores (sum to 1), the iteration count,
    and whether convergence was reached within tolerance.
    """
    if nodes <= 0:
        raise ValueError("nodes must be a positive integer")
    n = int(nodes)
    if n > MAX_NODES:
        raise ValueError(f"nodes exceeds MAX_NODES ({MAX_NODES})")
    if not (0.0 < damping < 1.0):
        raise ValueError("damping must be in the open interval (0, 1)")

    M = build_transition_matrix(n, edges)
    teleport = (1.0 - damping) / n

    r = np.full(n, 1.0 / n, dtype=np.float64)  # uniform prior
    converged = False
    iterations = 0
    for k in range(1, max_iter + 1):
        r_next = damping * (M @ r) + teleport
        # Renormalize defensively against float drift (M is column-stochastic, so the
        # mass is conserved analytically; this just kills accumulated rounding error).
        r_next /= r_next.sum()
        delta = float(np.abs(r_next - r).sum())
        r = r_next
        iterations = k
        if delta < tol:
            converged = True
            break

    return {
        "scores": [float(x) for x in r],
        "iterations": iterations,
        "converged": converged,
    }


def run(d: dict[str, Any]) -> dict[str, Any]:
    """Capability-handler entry point: validate the input dict and run PageRank."""
    nodes = int(d.get("nodes", 0))
    edges = d.get("edges", []) or []
    damping = float(d.get("damping", DEFAULT_DAMPING))
    return pagerank(nodes, list(edges), damping=damping)
