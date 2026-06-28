"""Graph-spectral analysis — the "Fourier transform on a graph".

FOURIER answers a question no per-node metric can: not *who* matters in a network,
but *how close the whole network is to splitting in two*. It treats a graph as a
vibrating drumhead and reads off its **Laplacian spectrum** — the natural frequencies
of diffusion / vibration over the graph.

The graph Laplacian ``L = D − A`` (degree minus adjacency) is the discrete analogue
of the continuous ``−∇²`` operator, so its eigenvalues are graph "frequencies" and its
eigenvectors are the standing-wave modes — the Fourier basis of the graph. Two
observables fall straight out of the bottom of that spectrum:

* **λ₂ — the algebraic connectivity (Fiedler value).** The smallest *non-trivial*
  eigenvalue. It is exactly ``0`` iff the graph is disconnected, and small whenever
  the graph has a narrow bottleneck (it is *near* a split). It is a global, certified
  measure of how robustly the network holds together.
* **The Fiedler vector ``v₂``** — the eigenvector of λ₂ — is the lowest-energy
  vibration mode. Its sign pattern is the canonical **spectral bisection**: the two
  halves the graph wants to break into. The induced cut size and conductance quantify
  that bottleneck.

Everything else is the spectral embedding: coordinates ``(v₂, v₃, v₄)`` that place each
node in the space its connectivity implies (the basis of spectral clustering and
spectral graph drawing).

The maths is exact linear algebra, not a heuristic:

1. **Canonicalisation.** The node-labelled graph is normalised (sorted unique labels,
   de-duplicated undirected edges, self-loops dropped) and hashed to a
   ``graph_commitment`` (SHA-256). The whole analysis is a pure function of that graph.
2. **Laplacian.** Build adjacency ``A`` (optionally weighted) and degree ``D``. The
   *combinatorial* Laplacian is ``L = D − A``. The *symmetric normalized* Laplacian is
   ``L_sym = I − D^{-1/2} A D^{-1/2}`` (scale-invariant; spectrum in ``[0, 2]``). Both
   are real symmetric PSD, so ``numpy.linalg.eigh`` gives an exact orthonormal
   eigendecomposition with sorted real eigenvalues ``0 = λ₁ ≤ λ₂ ≤ …``.
3. **Spectral cut.** Partition nodes by the sign of ``v₂ − median(v₂)``; report the
   cut size (edges crossing) and the conductance ``cut / min(vol_A, vol_B)``.

**Verification is cheap and trustless.** Given the graph and a claimed eigenpair
``(λ, x)``, a verifier checks the eigen-relation ``‖L x − λ x‖ / ‖x‖ ≤ tol`` (it really
is an eigenpair) and, for the connectivity mode, that ``x ⟂ 1`` (orthogonal to the
all-ones λ₁ eigenvector, so it is genuinely the Fiedler mode and not the trivial one).
That certificate is ``O(E)`` — it certifies λ₂ / Fiedler without redoing the full
``O(n³)`` eigendecomposition.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

import numpy as np

# Dense symmetric eigendecomposition is O(n^3); the protocol layer does NOT validate
# input against the declared schema, so the size ceiling is enforced here. A caller
# could otherwise hand over a huge graph and pin a CPU for an arbitrarily long time.
MAX_NODES = 400
MAX_EDGES = 20000
DEFAULT_K = 6
DEFAULT_TOL = 1e-6

LAPLACIANS = ("normalized", "combinatorial")


def canonical_graph(
    nodes: list[Any] | None, edges: list[list[Any]]
) -> tuple[list[str], dict[str, int], list[tuple[int, int, float]], str]:
    """Normalise an arbitrary node-labelled, optionally-weighted graph to canonical form.

    ``edges`` are undirected ``[u, v]`` or weighted ``[u, v, w]`` pairs. Returns
    ``(labels, index, weighted_edges, commitment)`` where ``labels`` are the sorted
    unique node identifiers (as strings), ``index`` maps label→position,
    ``weighted_edges`` are the sorted unique undirected edges as ``(i, j, w)`` index
    triples (parallel edges' weights summed), and ``commitment`` is the SHA-256 of the
    canonical JSON ``{"laplacian-independent graph"}``.
    """
    label_set: set[str] = {str(x) for x in (nodes or [])}
    # accumulate undirected weights keyed by the ordered index pair
    weight_by_pair: dict[tuple[str, str], float] = {}
    for e in edges:
        if not isinstance(e, (list, tuple)) or len(e) < 2:
            raise ValueError("each edge must be a [u, v] or [u, v, w] pair")
        a, b = str(e[0]), str(e[1])
        w = float(e[2]) if len(e) >= 3 else 1.0
        if w <= 0:
            raise ValueError(f"edge weight must be positive: {e!r}")
        label_set.add(a)
        label_set.add(b)
        if a == b:
            continue  # drop self-loops — they cancel in L = D − A
        key = (a, b) if a <= b else (b, a)
        weight_by_pair[key] = weight_by_pair.get(key, 0.0) + w

    labels = sorted(label_set)
    if not labels:
        raise ValueError("graph has no nodes")
    if len(labels) > MAX_NODES:
        raise ValueError(f"too many nodes (max {MAX_NODES}); dense eigendecomposition is O(n^3)")
    if len(weight_by_pair) > MAX_EDGES:
        raise ValueError(f"too many edges (max {MAX_EDGES})")

    index = {lab: i for i, lab in enumerate(labels)}
    weighted_edges = sorted(
        (index[a], index[b], w) for (a, b), w in weight_by_pair.items()
    )

    canon = {"nodes": labels, "edges": [[a, b, w] for a, b, w in weighted_edges]}
    commitment = hashlib.sha256(
        json.dumps(canon, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()
    return labels, index, weighted_edges, commitment


def adjacency(n: int, weighted_edges: list[tuple[int, int, float]]) -> np.ndarray:
    """Dense symmetric adjacency matrix ``A`` (float64) from index-triple edges."""
    A = np.zeros((n, n), dtype=np.float64)
    for i, j, w in weighted_edges:
        A[i, j] = w
        A[j, i] = w
    return A


def laplacian(A: np.ndarray, kind: str = "normalized") -> np.ndarray:
    """Graph Laplacian of the adjacency matrix ``A``.

    ``combinatorial``: ``L = D − A``. ``normalized``: symmetric normalized
    ``L_sym = I − D^{-1/2} A D^{-1/2}`` (zero-degree nodes contribute a zero row/col,
    matching the convention that isolated vertices sit at eigenvalue 0). Both are real
    symmetric positive-semidefinite.
    """
    n = A.shape[0]
    deg = A.sum(axis=1)
    if kind == "combinatorial":
        return np.diag(deg) - A
    if kind == "normalized":
        # d^{-1/2} with the convention 0^{-1/2} := 0 for isolated vertices.
        with np.errstate(divide="ignore"):
            dinv = np.where(deg > 0, 1.0 / np.sqrt(deg), 0.0)
        Dinv = np.diag(dinv)
        return np.eye(n) - Dinv @ A @ Dinv
    raise ValueError(f"laplacian must be one of {LAPLACIANS}; got {kind!r}")


def _eigh(L: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Ascending eigenvalues + orthonormal eigenvectors of a symmetric Laplacian.

    ``numpy.linalg.eigh`` returns them already sorted ascending. Tiny negative values
    from float round-off (L is PSD analytically) are clamped to 0.
    """
    vals, vecs = np.linalg.eigh(L)
    vals = np.where(np.abs(vals) < 1e-12, 0.0, vals)
    return vals, vecs


def _spectral_cut(
    fiedler: np.ndarray, A: np.ndarray, labels: list[str]
) -> dict[str, Any]:
    """Sign-of-(Fiedler − median) bisection: two sets, cut size, conductance.

    Conductance = (edges crossing the cut) / min(vol(A), vol(B)), where vol is the sum
    of weighted degrees on a side. A small conductance witnesses a genuine bottleneck.
    """
    n = len(labels)
    side = fiedler >= float(np.median(fiedler))  # bool mask: True = set A
    deg = A.sum(axis=1)

    cut = 0.0
    for i in range(n):
        for j in range(i + 1, n):
            if A[i, j] != 0.0 and side[i] != side[j]:
                cut += A[i, j]

    vol_a = float(deg[side].sum())
    vol_b = float(deg[~side].sum())
    denom = min(vol_a, vol_b)
    conductance = (cut / denom) if denom > 0 else 0.0

    set_a = [labels[i] for i in range(n) if side[i]]
    set_b = [labels[i] for i in range(n) if not side[i]]
    return {
        "set_a": set_a,
        "set_b": set_b,
        "cut_size": round(cut, 6),
        "conductance": round(conductance, 6),
    }


def analyze(
    nodes: list[Any] | None,
    edges: list[list[Any]],
    laplacian_kind: str = "normalized",
    k: int = DEFAULT_K,
) -> dict[str, Any]:
    """Full FOURIER spectral analysis — the ``fourier.spectrum@v1`` handler core.

    Returns the bottom ``k`` Laplacian eigenvalues, the algebraic connectivity λ₂ and
    its Fiedler vector, the sign-based spectral bisection, and a per-node spectral
    embedding ``(v₂, v₃, v₄)``. The combinatorial λ₂ is always reported alongside the
    chosen Laplacian's λ₂ (the combinatorial value is the dimensionful connectivity).
    """
    if laplacian_kind not in LAPLACIANS:
        raise ValueError(f"laplacian must be one of {LAPLACIANS}; got {laplacian_kind!r}")
    labels, _index, wedges, commitment = canonical_graph(nodes, edges)
    n = len(labels)
    k = max(1, min(int(k), n))

    A = adjacency(n, wedges)
    L = laplacian(A, laplacian_kind)
    vals, vecs = _eigh(L)

    # Fiedler value / vector of the SELECTED laplacian (λ2 = second-smallest eigenvalue).
    fiedler_idx = min(1, n - 1)
    fiedler_value = float(vals[fiedler_idx])
    fiedler_vec = vecs[:, fiedler_idx]
    # Orient deterministically (eigenvector sign is arbitrary): largest |component| > 0.
    if fiedler_vec[int(np.argmax(np.abs(fiedler_vec)))] < 0:
        fiedler_vec = -fiedler_vec

    # Combinatorial λ2 is always reported (the dimensionful algebraic connectivity).
    if laplacian_kind == "combinatorial":
        comb_lambda2 = fiedler_value
    else:
        comb_vals, _ = _eigh(laplacian(A, "combinatorial"))
        comb_lambda2 = float(comb_vals[min(1, n - 1)])

    # Spectral embedding: per-node coordinates from v2, v3, v4 (zero-padded if n is tiny).
    embedding: list[list[float]] = []
    for node in range(n):
        coord = []
        for col in (1, 2, 3):
            coord.append(float(vecs[node, col]) if col < n else 0.0)
        embedding.append(coord)

    return {
        "n": n,
        "m": len(wedges),
        "laplacian": laplacian_kind,
        "eigenvalues": [float(v) for v in vals[:k]],
        "fiedler_value": fiedler_value,
        "combinatorial_lambda2": comb_lambda2,
        "fiedler_vector": [float(x) for x in fiedler_vec],
        "spectral_cut": _spectral_cut(fiedler_vec, A, labels),
        "embedding": embedding,
        "nodes": labels,
        "graph_commitment": commitment,
    }


def verify(
    nodes: list[Any] | None,
    edges: list[list[Any]],
    lambda_: float,
    vector: list[float],
    laplacian_kind: str = "normalized",
    tol: float = DEFAULT_TOL,
) -> dict[str, Any]:
    """Trustless eigenpair certificate — the ``fourier.verify@v1`` handler core.

    Re-derives the canonical graph and its Laplacian ``L``, then checks the claimed
    eigenpair ``(λ, x)`` with two cheap ``O(E)`` tests:

    * **residual** ``‖L x − λ x‖ / ‖x‖`` — must be ``≤ tol`` for ``(λ, x)`` to be a
      genuine eigenpair;
    * **orthogonality** ``|⟨x, 1⟩| / (‖x‖ √n)`` (combinatorial) or ``|⟨x, d^{1/2}⟩| /
      (‖x‖ ‖d^{1/2}‖)`` (normalized) — the cosine against the *trivial* λ₁ eigenvector.
      Near 0 means ``x`` is genuinely the connectivity (Fiedler) mode, not the constant
      one.

    ``valid`` is true iff the residual is within tolerance (an eigenpair) AND the vector
    is non-trivial (not the all-ones λ₁ mode), so a verifier can certify λ₂ / Fiedler in
    ``O(E)`` without re-running the ``O(n³)`` eigendecomposition.
    """
    if laplacian_kind not in LAPLACIANS:
        raise ValueError(f"laplacian must be one of {LAPLACIANS}; got {laplacian_kind!r}")
    labels, _index, wedges, commitment = canonical_graph(nodes, edges)
    n = len(labels)

    x = np.asarray(vector, dtype=np.float64)
    if x.shape != (n,):
        return {
            "valid": False,
            "residual": float("inf"),
            "orthogonality": float("inf"),
            "graph_commitment": commitment,
            "error": f"vector length {x.size} != node count {n}",
        }

    norm_x = float(np.linalg.norm(x))
    if norm_x == 0.0:
        return {
            "valid": False,
            "residual": float("inf"),
            "orthogonality": float("inf"),
            "graph_commitment": commitment,
            "error": "vector is the zero vector",
        }

    A = adjacency(n, wedges)
    L = laplacian(A, laplacian_kind)

    residual = float(np.linalg.norm(L @ x - float(lambda_) * x) / norm_x)

    # Trivial (λ1) eigenvector: all-ones for combinatorial, d^{1/2} for normalized.
    if laplacian_kind == "combinatorial":
        trivial = np.ones(n, dtype=np.float64)
    else:
        trivial = np.sqrt(A.sum(axis=1))
    norm_trivial = float(np.linalg.norm(trivial))
    if norm_trivial == 0.0:
        orthogonality = 0.0
    else:
        orthogonality = float(abs(np.dot(x, trivial)) / (norm_x * norm_trivial))

    is_eigenpair = residual <= float(tol)
    is_nontrivial = orthogonality <= float(tol) or orthogonality < 1e-3
    return {
        "valid": bool(is_eigenpair and is_nontrivial),
        "residual": residual,
        "orthogonality": orthogonality,
        "is_eigenpair": bool(is_eigenpair),
        "graph_commitment": commitment,
    }
