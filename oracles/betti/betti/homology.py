"""Persistent homology over Z/2 — the mathematics Betti actually sells.

Pure numpy + pure-Python (scipy is NOT available in this environment). We build a
Vietoris-Rips filtration of a point cloud, run the standard column-reduction of the
GF(2) boundary matrix to read off persistence pairs per dimension, and derive the
Betti curves b_k(scale). A bottleneck distance between two diagrams gives a
topology-drift metric.

HARD CAPS (the protocol layer does NOT validate input — see chronos/percola): a Rips
complex is combinatorially explosive (triangles ~ O(n^3), tetrahedra ~ O(n^4)), so we
cap the number of points and the total number of simplices and *report* when we clip,
rather than silently truncating.
"""

from __future__ import annotations

import itertools
from typing import Any

import numpy as np

# ---- hard caps (refuse / clip beyond these and SAY SO in the output) --------
MAX_POINTS = 300            # a Rips complex over n points explodes; cap n hard
MAX_SIMPLICES = 150_000     # total simplices generated across all dimensions
MAX_DIM = 2                 # we go up to triangles (b1) and tetrahedra (b2)
MAX_CURVE_STEPS = 200       # resolution ceiling of the Betti curve


# =============================================================================
#  Vietoris-Rips filtration
# =============================================================================

def _pairwise_dist(points: np.ndarray) -> np.ndarray:
    """Full n×n Euclidean distance matrix (n is capped, so n^2 is fine)."""
    diff = points[:, None, :] - points[None, :, :]
    return np.sqrt(np.einsum("ijk,ijk->ij", diff, diff))


def _auto_max_scale(dist: np.ndarray) -> float:
    """Default scale: half the cloud diameter — enough to merge it into one blob
    and let the largest features (loops/voids) be born and die."""
    diam = float(dist.max()) if dist.size else 0.0
    return diam * 0.5 if diam > 0 else 1.0


def build_rips(points: np.ndarray, max_scale: float, max_dim: int) -> tuple[list[dict[str, Any]], bool]:
    """Build the Rips complex up to `max_dim`, keeping simplices whose filtration
    value (= longest edge among its vertices) is <= max_scale.

    Returns (simplices, capped). Each simplex is a dict:
        {"verts": tuple[int,...], "dim": int, "birth": float}
    `capped` is True if we hit MAX_SIMPLICES and stopped adding higher simplices.

    Simplices are emitted in increasing dimension; the caller sorts them into
    filtration order for the reduction.
    """
    n = len(points)
    dist = _pairwise_dist(points)

    simplices: list[dict[str, Any]] = []
    # 0-simplices (vertices) are born at scale 0.
    for i in range(n):
        simplices.append({"verts": (i,), "dim": 0, "birth": 0.0})

    # 1-simplices (edges): present when the pair distance <= max_scale.
    edge_birth: dict[tuple[int, int], float] = {}
    adj: list[set[int]] = [set() for _ in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            d = float(dist[i, j])
            if d <= max_scale:
                edge_birth[(i, j)] = d
                adj[i].add(j)
                adj[j].add(i)
                simplices.append({"verts": (i, j), "dim": 1, "birth": d})

    capped = False
    if len(simplices) >= MAX_SIMPLICES:
        return simplices[:MAX_SIMPLICES], True

    # 2-simplices (triangles): all three edges must exist. Birth = max edge length.
    if max_dim >= 1:
        for i in range(n):
            for j in adj[i]:
                if j <= i:
                    continue
                # common neighbours k > j with all three edges present
                for k in adj[i] & adj[j]:
                    if k <= j:
                        continue
                    b = max(edge_birth[(i, j)], edge_birth[(i, k)], edge_birth[(j, k)])
                    simplices.append({"verts": (i, j, k), "dim": 2, "birth": b})
                    if len(simplices) >= MAX_SIMPLICES:
                        return simplices[:MAX_SIMPLICES], True

    # 3-simplices (tetrahedra) — needed for a TRUE b2 (a cavity is bounded by faces).
    if max_dim >= 2:
        tri_birth: dict[tuple[int, int, int], float] = {
            s["verts"]: s["birth"] for s in simplices if s["dim"] == 2
        }
        for i in range(n):
            for j, k, l in itertools.combinations(sorted(x for x in adj[i] if x > i), 3):
                # all four triangular faces of (i,j,k,l) must already exist
                faces = [(i, j, k), (i, j, l), (i, k, l), (j, k, l)]
                if all(f in tri_birth for f in faces):
                    b = max(tri_birth[f] for f in faces)
                    simplices.append({"verts": (i, j, k, l), "dim": 3, "birth": b})
                    if len(simplices) >= MAX_SIMPLICES:
                        return simplices[:MAX_SIMPLICES], True

    return simplices, capped


# =============================================================================
#  Standard persistence: GF(2) column reduction
# =============================================================================

def _sorted_order(simplices: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Sort by (filtration value, dimension, vertices) so every face precedes its
    cofaces — a valid filtration order for the boundary reduction."""
    return sorted(simplices, key=lambda s: (s["birth"], s["dim"], s["verts"]))


def reduce_persistence(simplices: list[dict[str, Any]], max_dim: int) -> dict[int, list[list[float]]]:
    """Standard reduction algorithm over GF(2).

    Sort simplices into filtration order; build the boundary matrix as columns of
    sets of row indices; reduce left-to-right, repeatedly adding the column that
    currently owns this column's low-row pivot until the pivot is unique (or the
    column empties). A nonempty reduced column with pivot `p` pairs death-simplex
    (this column) with birth-simplex `p`; an empty column whose simplex is never
    used as a pivot is an essential (infinite) bar.

    Returns {dim: [[birth, death], ...]} with death == inf for unpaired bars. We
    keep bars up to homology dimension `max_dim` (H_k needs (k+1)-simplices, which
    build_rips already provides up to dim 3 → H_2).

    Complexity: O(m^3) worst case in the number of simplices m (standard, no
    twist/clearing). m is bounded by MAX_SIMPLICES, so this is the documented cap.
    """
    order = _sorted_order(simplices)
    index_of = {s["verts"]: idx for idx, s in enumerate(order)}

    # boundary columns: for each simplex, the set of its codim-1 faces (as indices)
    columns: list[set[int]] = []
    for s in order:
        v = s["verts"]
        if len(v) == 1:
            columns.append(set())
        else:
            faces = [v[:i] + v[i + 1:] for i in range(len(v))]
            columns.append({index_of[f] for f in faces})

    low_to_col: dict[int, int] = {}   # pivot row -> column index that owns it
    pairs: list[tuple[int, int]] = []  # (birth_simplex_idx, death_simplex_idx)

    for j in range(len(columns)):
        col = columns[j]
        while col:
            low = max(col)  # low-row pivot
            if low in low_to_col:
                # add (XOR over GF(2)) the earlier column that owns this pivot
                col ^= columns[low_to_col[low]]
            else:
                low_to_col[low] = j
                pairs.append((low, j))
                break
        columns[j] = col  # store reduced column (now empty or with a unique pivot)

    paired_births = {b for b, _ in pairs}

    diagram: dict[int, list[list[float]]] = {k: [] for k in range(max_dim + 1)}

    # finite bars from pairs
    for b_idx, d_idx in pairs:
        dim = order[b_idx]["dim"]
        if dim > max_dim:
            continue
        birth = order[b_idx]["birth"]
        death = order[d_idx]["birth"]
        if death > birth:  # drop zero-persistence bars (born & killed at same scale)
            diagram[dim].append([birth, death])

    # essential (infinite) bars: simplices that are neither a death nor a paired birth
    death_cols = {d for _, d in pairs}
    for idx, s in enumerate(order):
        if s["dim"] > max_dim:
            continue
        if idx in death_cols or idx in paired_births:
            continue
        diagram[s["dim"]].append([s["birth"], float("inf")])

    for k in diagram:
        diagram[k].sort()
    return diagram


# =============================================================================
#  Union-find cross-check for b0 (fast, independent of the matrix reduction)
# =============================================================================

def b0_unionfind(points: np.ndarray, scale: float) -> int:
    """Number of connected components at `scale` via union-find over edges with
    length <= scale. Independent oracle for the matrix-derived b0."""
    n = len(points)
    if n == 0:
        return 0
    dist = _pairwise_dist(points)
    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i in range(n):
        for j in range(i + 1, n):
            if dist[i, j] <= scale:
                ri, rj = find(i), find(j)
                if ri != rj:
                    parent[ri] = rj
    return len({find(i) for i in range(n)})


# =============================================================================
#  Betti curve + counts at a scale
# =============================================================================

def betti_at(diagram: dict[int, list[list[float]]], scale: float, k: int) -> int:
    """b_k(scale) = number of dim-k bars alive at `scale` (birth <= scale < death,
    inf death always counts)."""
    bars = diagram.get(k, [])
    return sum(1 for b, d in bars if b <= scale and (d == float("inf") or scale < d))


def betti_curve(diagram: dict[int, list[list[float]]], max_scale: float, num_steps: int) -> list[dict[str, float]]:
    """Sample b0,b1,b2 across [0, max_scale] at `num_steps` evenly spaced scales."""
    steps = max(2, min(int(num_steps), MAX_CURVE_STEPS))
    curve: list[dict[str, float]] = []
    for i in range(steps):
        s = max_scale * i / (steps - 1)
        curve.append({
            "scale": round(s, 6),
            "b0": betti_at(diagram, s, 0),
            "b1": betti_at(diagram, s, 1),
            "b2": betti_at(diagram, s, 2),
        })
    return curve


# =============================================================================
#  Bottleneck distance between two persistence diagrams
# =============================================================================

def _linf(p: list[float], q: list[float]) -> float:
    return max(abs(p[0] - q[0]), abs(p[1] - q[1]))


def _diag_dist(p: list[float]) -> float:
    """L_inf distance from a point to the diagonal = (death - birth) / 2."""
    return (p[1] - p[0]) / 2.0


def _finite_points(bars: list[list[float]], cap_inf: float) -> list[list[float]]:
    """Replace infinite deaths with a large finite cap so essential bars still
    participate in the matching (and two diagrams with the same essential class
    match at ~0)."""
    out = []
    for b, d in bars:
        out.append([b, cap_inf if d == float("inf") else d])
    return out


def bottleneck(dgm_a: list[list[float]], dgm_b: list[list[float]], cap_inf: float) -> float:
    """Exact bottleneck distance for the (capped) diagrams: minimise, over a perfect
    matching that may send any point to its diagonal projection, the maximum L_inf
    cost of a matched pair.

    Implementation: binary search on epsilon + a Hopcroft-Karp perfect-matching
    feasibility test on the threshold bipartite graph. Both diagrams are augmented
    with the diagonal projections of the *other* diagram's points so that any point
    is allowed to match the diagonal; diagonal-to-diagonal pairs cost 0. This is the
    standard reduction and is exact.

    Complexity: O(E·sqrt(V)) per feasibility check × O(log(1/tol)) bisection steps,
    where V <= 2·(|A|+|B|) — fine for the capped diagram sizes.
    """
    A = _finite_points(dgm_a, cap_inf)
    B = _finite_points(dgm_b, cap_inf)
    if not A and not B:
        return 0.0

    # Augment: left = A points + diagonal-projections of B; right = B points +
    # diagonal-projections of A. A real point may match a real point or its own
    # diagonal projection; projection↔projection always matches at cost 0.
    nA, nB = len(A), len(B)
    left = list(A) + [None] * nB   # None = diagonal slot (projection of B[k])
    right = list(B) + [None] * nA  # None = diagonal slot (projection of A[k])
    nL = len(left)

    def cost(i: int, j: int) -> float:
        li, rj = left[i], right[j]
        if li is not None and rj is not None:
            return _linf(li, rj)
        if li is not None and rj is None:
            # A[i] to its diagonal projection: only the diagonal slot at index nB+i
            return _diag_dist(li) if j == nB + i else float("inf")
        if li is None and rj is not None:
            # diagonal projection of B[j] (left slot nA + j) to B[j]
            return _diag_dist(rj) if i == nA + j else float("inf")
        # both diagonal: free, but only the "aligned" diagonal pairing
        return 0.0

    # candidate epsilons: every finite pairwise cost (the optimum is one of them)
    cands = {0.0}
    for i in range(nL):
        for j in range(nL):
            c = cost(i, j)
            if c != float("inf"):
                cands.add(c)
    candidates = sorted(cands)

    def feasible(eps: float) -> bool:
        # bipartite graph: edge i-j iff cost(i,j) <= eps; need a perfect matching
        adj: list[list[int]] = [[] for _ in range(nL)]
        for i in range(nL):
            for j in range(nL):
                if cost(i, j) <= eps + 1e-12:
                    adj[i].append(j)
        match_r = [-1] * nL

        def try_kuhn(u: int, seen: list[bool]) -> bool:
            for v in adj[u]:
                if not seen[v]:
                    seen[v] = True
                    if match_r[v] == -1 or try_kuhn(match_r[v], seen):
                        match_r[v] = u
                        return True
            return False

        matched = 0
        for u in range(nL):
            seen = [False] * nL
            if try_kuhn(u, seen):
                matched += 1
        return matched == nL

    # binary search over the sorted candidate costs for the smallest feasible eps
    lo, hi = 0, len(candidates) - 1
    if feasible(candidates[lo]):
        return candidates[lo]
    while lo < hi:
        mid = (lo + hi) // 2
        if feasible(candidates[mid]):
            hi = mid
        else:
            lo = mid + 1
    return candidates[lo]


# =============================================================================
#  Top-level handlers (validate + clamp, then compute)
# =============================================================================

def _coerce_points(raw: Any) -> np.ndarray:
    if raw is None:
        raise ValueError("missing 'points'")
    arr = np.asarray(raw, dtype=float)
    if arr.ndim != 2 or arr.shape[0] < 1 or arr.shape[1] < 1:
        raise ValueError("'points' must be a non-empty n×d array of numbers")
    if not np.isfinite(arr).all():
        raise ValueError("'points' contains non-finite values")
    return arr


def homology(
    points_raw: Any,
    max_scale: float | None = None,
    max_dim: int = 2,
    num_steps: int = 40,
) -> dict[str, Any]:
    """betti.homology handler. Validates + hard-caps, builds the Rips filtration,
    reduces persistence, returns Betti numbers, the Betti curve, and the diagram."""
    points = _coerce_points(points_raw)

    notes = []
    if len(points) > MAX_POINTS:
        points = points[:MAX_POINTS]
        notes.append(f"clipped to first {MAX_POINTS} of {len(points_raw)} points (point cap)")

    max_dim = max(1, min(int(max_dim), MAX_DIM))
    n, d = int(points.shape[0]), int(points.shape[1])

    dist = _pairwise_dist(points)
    scale = float(max_scale) if max_scale is not None else _auto_max_scale(dist)
    if scale <= 0:
        raise ValueError("max_scale must be positive")

    simplices, capped = build_rips(points, scale, max_dim)
    if capped:
        notes.append(f"simplex count hit the cap ({MAX_SIMPLICES}); higher simplices were not generated")

    diagram = reduce_persistence(simplices, max_dim)

    # b0 cross-check via union-find (independent of the matrix reduction)
    b0_uf = b0_unionfind(points, scale)

    betti = {
        "b0": betti_at(diagram, scale, 0),
        "b1": betti_at(diagram, scale, 1),
        "b2": betti_at(diagram, scale, 2),
    }

    return {
        "n": n,
        "d": d,
        "betti": betti,
        "betti_curve": betti_curve(diagram, scale, num_steps),
        "diagram": {str(k): diagram.get(k, []) for k in range(max_dim + 1)},
        "max_scale": round(scale, 6),
        "max_dim": max_dim,
        "simplices_count": len(simplices),
        "b0_unionfind": b0_uf,
        "capped": capped,
        "notes": notes,
    }


def _diagram_for_dim(points: np.ndarray, scale: float, dim: int) -> tuple[list[list[float]], float]:
    """Persistence diagram for a single homology dimension `dim`, plus the scale used
    (for the infinite-bar cap in the bottleneck distance)."""
    max_dim = max(1, min(dim, MAX_DIM))
    simplices, _ = build_rips(points, scale, max_dim)
    diagram = reduce_persistence(simplices, max_dim)
    return diagram.get(dim, []), scale


def distance(
    points_a_raw: Any,
    points_b_raw: Any,
    dim: int = 1,
    max_scale: float | None = None,
) -> dict[str, Any]:
    """betti.distance handler. Computes each cloud's persistence diagram in homology
    dimension `dim` and returns the bottleneck distance — a topology-drift metric
    (small = same shape, large = topology changed)."""
    a = _coerce_points(points_a_raw)
    b = _coerce_points(points_b_raw)
    if len(a) > MAX_POINTS:
        a = a[:MAX_POINTS]
    if len(b) > MAX_POINTS:
        b = b[:MAX_POINTS]

    dim = max(0, min(int(dim), MAX_DIM))

    # shared scale so the two diagrams live in the same filtration window
    da, db = _pairwise_dist(a), _pairwise_dist(b)
    if max_scale is not None:
        scale = float(max_scale)
    else:
        scale = max(_auto_max_scale(da), _auto_max_scale(db))
    if scale <= 0:
        raise ValueError("max_scale must be positive")

    dgm_a, _ = _diagram_for_dim(a, scale, dim)
    dgm_b, _ = _diagram_for_dim(b, scale, dim)

    cap_inf = scale  # essential bars treated as dying at the window edge
    dist_b = bottleneck(dgm_a, dgm_b, cap_inf)

    return {
        "dim": dim,
        "bottleneck": round(dist_b, 6),
        "max_scale": round(scale, 6),
        "diagram_a": dgm_a,
        "diagram_b": dgm_b,
    }
