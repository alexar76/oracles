"""Blue-noise / structured sampling via Mitchell's best-candidate algorithm.

A *blue-noise* point set has a power spectrum dominated by high frequencies: the
points are spread evenly with no low-frequency clumps and no regular grid aliasing.
Equivalently, the **minimum pairwise distance is large** relative to a uniform
i.i.d. random set of the same size — there are no two points sitting on top of each
other, yet the arrangement stays irregular (no visible lattice).

Mitchell's best-candidate is a dart-throwing scheme that produces this cheaply and
incrementally: to place point *i*, draw ``candidates`` uniform random candidates,
and keep the one whose distance to the *nearest already-placed point* is largest.
Greedily maximising the nearest-neighbour gap pushes every new point into the
biggest empty region, yielding the characteristic even-but-irregular spacing used
in stippling, anti-aliasing, Poisson-disk-like sampling, Monte-Carlo integration,
and procedural placement.

Determinism: pass a ``seed`` to get a reproducible set from
``numpy.random.default_rng(seed)``. With no seed we mix true OS entropy
(``os.urandom``) into the generator and *report the seed we used* so a caller can
reproduce the exact set later.
"""

from __future__ import annotations

import os
from typing import Any

import numpy as np

# Hard limits for the capability (kept in sync with the input schema).
MAX_COUNT = 2048
MAX_CANDIDATES = 1024
DEFAULT_CANDIDATES = 10


def _resolve_seed(seed: int | None) -> tuple[int, str]:
    """Return (seed, source). If no seed is given, draw a fresh one from os.urandom."""
    if seed is not None:
        return int(seed) & 0xFFFFFFFFFFFFFFFF, "provided"
    fresh = int.from_bytes(os.urandom(8), "big")
    return fresh, "os.urandom"


def min_pairwise_distance(points: np.ndarray) -> float:
    """Smallest Euclidean distance between any two distinct points (0.0 if <2)."""
    n = len(points)
    if n < 2:
        return 0.0
    best = float("inf")
    # O(n^2) but n <= MAX_COUNT; clear and exact (no kd-tree dependency).
    for i in range(n - 1):
        diff = points[i + 1 :] - points[i]
        d = float(np.sqrt(np.min(np.einsum("ij,ij->i", diff, diff))))
        if d < best:
            best = d
    return best


def bluenoise(
    count: int,
    candidates: int = DEFAULT_CANDIDATES,
    seed: int | None = None,
) -> dict[str, Any]:
    """Generate a blue-noise point set in [0,1)^2 via Mitchell's best-candidate.

    Parameters
    ----------
    count:       number of points to generate (1..MAX_COUNT).
    candidates:  candidates considered per placement (>=1). Larger = more even
                 spacing (bigger minimum distance) at higher cost.
    seed:        optional integer seed for reproducibility. If omitted, a seed is
                 drawn from os.urandom and reported back.

    Returns a dict with ``points`` (list of [x, y]), ``count``, ``min_distance``,
    ``candidates``, ``seed`` and ``seed_source``.
    """
    count = int(count)
    if count < 1 or count > MAX_COUNT:
        raise ValueError(f"count must be in 1..{MAX_COUNT}, got {count}")
    candidates = int(candidates)
    if candidates < 1 or candidates > MAX_CANDIDATES:
        raise ValueError(f"candidates must be in 1..{MAX_CANDIDATES}, got {candidates}")

    used_seed, source = _resolve_seed(seed)
    rng = np.random.default_rng(used_seed)

    pts = np.empty((count, 2), dtype=np.float64)
    # First point: a single uniform sample. (No prior points to push away from.)
    pts[0] = rng.random(2)

    for i in range(1, count):
        cand = rng.random((candidates, 2))  # candidates x 2 in [0,1)
        existing = pts[:i]  # i x 2
        # Squared distance from each candidate to each existing point.
        # diff: candidates x i x 2
        diff = cand[:, None, :] - existing[None, :, :]
        d2 = np.einsum("cij,cij->ci", diff, diff)  # candidates x i
        nearest = d2.min(axis=1)  # closest existing point per candidate
        pts[i] = cand[int(np.argmax(nearest))]  # keep the most isolated candidate

    return {
        "points": pts.tolist(),
        "count": count,
        "min_distance": min_pairwise_distance(pts),
        "candidates": candidates,
        "seed": used_seed,
        "seed_source": source,
    }


def expected_uniform_min_distance(count: int) -> float:
    """Heuristic expected nearest-neighbour gap for `count` uniform points in the unit
    square: ~ 0.5 / sqrt(count) for the *minimum* over all pairs. Used only for docs
    / sanity comparisons; the tests measure the real uniform set directly."""
    return 0.5 / np.sqrt(max(count, 1))
