"""Halton low-discrepancy (quasi-random) sequences.

White noise (i.i.d. uniform draws) clumps: by pure chance some regions get many
points and others get gaps. A *low-discrepancy* sequence is engineered so every
prefix of the sequence fills the unit cube as evenly as possible — its star
discrepancy D*_N shrinks like O((log N)^d / N) instead of the O(1/sqrt(N)) you
get from random sampling. That is the entire product: **more even space-filling
per sample**, which means quasi-Monte-Carlo integration, sampling and search that
converge faster than random and are fully *deterministic* (reproducible by anyone
with the same arguments — no seed, no entropy).

The Halton sequence builds a d-dimensional point by taking, for coordinate k, the
**van der Corput radical inverse** of the index n in the k-th prime base. The
radical inverse φ_b(n) writes n in base b and reflects its digits around the
decimal point:

    n = Σ a_i · b^i   (base-b digits a_i)
    φ_b(n) = Σ a_i · b^-(i+1)   ∈ [0, 1)

Because successive coordinates use *coprime* prime bases (2, 3, 5, 7, 11, ...),
the per-axis 1D sequences are jointly equidistributed and the whole point set
fills [0,1)^d without the lattice-alignment artefacts you'd get from a single
base. This module is pure, deterministic, and dependency-free.
"""

from __future__ import annotations

from typing import Any

MAX_COUNT = 4096
MAX_DIM = 8
# First MAX_DIM primes — successive coprime bases, one per coordinate axis.
PRIMES: list[int] = [2, 3, 5, 7, 11, 13, 17, 19]


def radical_inverse(n: int, base: int) -> float:
    """van der Corput radical inverse φ_base(n) in [0, 1).

    Reflect the base-`base` digits of `n` around the radix point. Uses the
    standard numerically-stable accumulation (divide a running fraction by the
    base each digit) so it stays exact for the index ranges we serve.
    """
    if base < 2:
        raise ValueError("base must be >= 2")
    result = 0.0
    f = 1.0 / base
    i = n
    while i > 0:
        digit = i % base
        result += digit * f
        i //= base
        f /= base
    return result


def halton(count: int, dim: int = 2, skip: int = 0) -> list[list[float]]:
    """Generate `count` points of the `dim`-dimensional Halton sequence.

    Each point lives in [0,1)^dim. Coordinate k is the radical inverse of the
    sample index in the k-th prime base. `skip` drops the first `skip` indices
    (a common trick to avoid the mildly-correlated start of the sequence).

    Deterministic: identical (count, dim, skip) always returns identical points.
    """
    count = int(count)
    dim = int(dim)
    skip = int(skip)
    if not (1 <= count <= MAX_COUNT):
        raise ValueError(f"count must be in 1..{MAX_COUNT}")
    if not (1 <= dim <= MAX_DIM):
        raise ValueError(f"dim must be in 1..{MAX_DIM}")
    if skip < 0:
        raise ValueError("skip must be >= 0")

    bases = PRIMES[:dim]
    # Index 0 maps to the origin in every base; conventionally Halton starts at 1.
    start = 1 + skip
    points: list[list[float]] = []
    for n in range(start, start + count):
        points.append([radical_inverse(n, b) for b in bases])
    return points


def run(count: int, dim: int = 2, skip: int = 0) -> dict[str, Any]:
    """Capability handler: generate the sequence and report its bases."""
    pts = halton(count, dim, skip)
    return {
        "sequence": "halton/van-der-corput",
        "points": pts,
        "dim": int(dim),
        "count": len(pts),
        "skip": int(skip),
        "bases": PRIMES[: int(dim)],
    }
