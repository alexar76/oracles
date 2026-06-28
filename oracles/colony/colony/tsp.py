"""Colony — combinatorial optimization with a quality certificate.

The travelling-salesman problem (TSP) is NP-hard, so an agent that needs a route
cannot, in general, afford to *prove* it found the shortest one. Colony instead
returns a **good** tour together with a **certificate of quality**: a real,
admissible lower bound on the optimal tour length and the resulting optimality
``gap``. The agent buys not just an answer but a *bound on how wrong the answer
could be* — which is exactly what you need to decide whether to ship the route or
pay for more compute.

Pipeline (all real, no mocks):

1. **Nearest-neighbour construction** — a greedy tour: from the current city always
   hop to the closest unvisited one, then close the loop. O(n^2), a sane starting
   point.
2. **2-opt local search** — repeatedly reverse a tour segment whenever doing so
   removes a crossing / shortens the tour. Converges to a 2-optimal tour whose
   length is never worse than the nearest-neighbour tour it started from.
3. **Lower bound** — for every node take its single cheapest incident edge, sum
   them, divide by two. Every tour visits each node with exactly two incident edges,
   so each node contributes at least its cheapest edge to *some* tour; summing the
   minimum incident edge per node double-counts edges, hence the ``/2``. This is a
   genuine admissible lower bound on the optimal (and therefore on *any*) tour, so
   ``length >= lower_bound`` always holds.

The reported ``gap = (length - lower_bound) / lower_bound`` is the certificate: the
true optimum lies somewhere in ``[lower_bound, length]``, so the returned tour is at
most ``gap`` fraction longer than optimal.
"""

from __future__ import annotations

from typing import Any

import numpy as np

MAX_NODES = 2000  # guard against pathological payloads
MAX_ITERATIONS = 100_000


def distance_matrix(points: np.ndarray) -> np.ndarray:
    """Full Euclidean distance matrix for an (n, 2) array of 2D points."""
    diff = points[:, None, :] - points[None, :, :]
    return np.sqrt((diff * diff).sum(axis=-1))


def tour_length(tour: list[int], D: np.ndarray) -> float:
    """Length of a closed tour (returns to the start)."""
    n = len(tour)
    total = 0.0
    for i in range(n):
        total += float(D[tour[i], tour[(i + 1) % n]])
    return total


def nearest_neighbour(D: np.ndarray, start: int = 0) -> list[int]:
    """Greedy nearest-neighbour construction from ``start``."""
    n = D.shape[0]
    unvisited = set(range(n))
    current = start
    unvisited.remove(current)
    tour = [current]
    while unvisited:
        # nearest unvisited city to `current`
        nxt = min(unvisited, key=lambda j: D[current, j])
        unvisited.remove(nxt)
        tour.append(nxt)
        current = nxt
    return tour


def two_opt(tour: list[int], D: np.ndarray, max_iterations: int = 1000) -> list[int]:
    """2-opt local search: reverse segments while it shortens the tour.

    Each accepted move strictly decreases the tour length, so the result is never
    longer than the input tour. Stops at a 2-optimal tour or when the iteration
    budget is exhausted.
    """
    n = len(tour)
    if n < 4:
        return list(tour)
    best = list(tour)
    improved = True
    iters = 0
    while improved and iters < max_iterations:
        improved = False
        for i in range(1, n - 1):
            a, b = best[i - 1], best[i]
            for k in range(i + 1, n):
                iters += 1
                if iters >= max_iterations:
                    improved = False
                    break
                c = best[k]
                d = best[(k + 1) % n]
                if d == a:
                    continue
                # gain of reversing best[i..k]: replace edges (a,b),(c,d) by (a,c),(b,d)
                before = D[a, b] + D[c, d]
                after = D[a, c] + D[b, d]
                if after + 1e-12 < before:
                    best[i : k + 1] = best[i : k + 1][::-1]
                    improved = True
                    a, b = best[i - 1], best[i]
            if iters >= max_iterations:
                break
    return best


def lower_bound(D: np.ndarray) -> float:
    """Admissible lower bound: sum of each node's cheapest incident edge, / 2.

    Every Hamiltonian tour uses exactly two edges at every node. The two used edges
    each cost at least the node's minimum incident edge, so 2 * L(tour) >=
    sum_i min_j!=i D[i,j], giving L(tour) >= (1/2) * sum_i min incident edge. This is
    a valid lower bound on the optimum and on any tour.
    """
    n = D.shape[0]
    masked = D.copy()
    np.fill_diagonal(masked, np.inf)
    return float(masked.min(axis=1).sum() / 2.0)


def solve(points: list[list[float]] | np.ndarray, iterations: int = 1000) -> dict[str, Any]:
    """Full pipeline for the capability handler.

    Returns the improved tour (a permutation of all n nodes), its length, an
    admissible lower bound, and the optimality gap.
    """
    pts = np.asarray(points, dtype=float)
    if pts.ndim != 2 or pts.shape[1] != 2:
        raise ValueError("points must be a list of [x, y] pairs")
    n = pts.shape[0]
    if n < 3:
        raise ValueError("need at least 3 points")
    if n > MAX_NODES:
        raise ValueError(f"too many points (max {MAX_NODES})")

    it = max(1, min(int(iterations), MAX_ITERATIONS))
    D = distance_matrix(pts)

    nn_tour = nearest_neighbour(D, start=0)
    nn_len = tour_length(nn_tour, D)

    opt_tour = two_opt(nn_tour, D, max_iterations=it)
    opt_len = tour_length(opt_tour, D)

    lb = lower_bound(D)
    gap = (opt_len - lb) / lb if lb > 0 else 0.0

    return {
        "tour": [int(x) for x in opt_tour],
        "length": opt_len,
        "lower_bound": lb,
        "gap": gap,
        "n": n,
        "nn_length": nn_len,
    }
