"""Robust consensus aggregation — the math behind Murmuration.

A set of agents each submit a scalar estimate of some quantity (a price, a
probability, a measurement). A naive arithmetic mean is *not* robust: a single
adversarial or faulty submission can drag it arbitrarily far. Murmuration returns
several breakdown-resistant location estimators plus a distributed-consensus
simulation, so a swarm of agents can settle on one trustworthy number.

Estimators
----------
* **median** — 50%% breakdown point; the most robust single statistic.
* **trimmed mean** — discard the lowest/highest ``trim`` fraction, average the
  rest. Tunable robustness/efficiency trade-off.
* **Tukey biweight location** — an M-estimator that smoothly *redescends*:
  points far from the centre (beyond ``c`` MADs) get exactly zero weight, so
  outliers cannot influence the fit at all. Solved by iteratively reweighted
  least squares (IRLS) seeded at the median.

DeGroot consensus
-----------------
Models the swarm as a network that repeatedly averages opinions. With a
row-stochastic *complete-graph* averaging matrix ``W`` (every agent listens to
everyone, including itself, with equal weight ``1/n``), the opinion vector
evolves as ``x_{k+1} = W x_k``. For the complete graph ``W x`` is just the
arithmetic mean broadcast to every coordinate, so the process converges in the
limit to the mean — and in exact arithmetic reaches it after a single step. We
iterate explicitly until the spread collapses below a tolerance and report the
iteration count, mirroring how a real boid flock tightens into one cluster.

Everything here is pure and deterministic; no global state, no I/O.
"""

from __future__ import annotations

from typing import Any

import numpy as np

# Tukey biweight tuning constant. c=6.0 → ~95% efficiency at the Gaussian while
# giving zero weight to anything beyond 6 MAD-scaled units from the centre.
BIWEIGHT_C = 6.0
_EPS = 1e-12


def _as_array(values: Any) -> np.ndarray:
    arr = np.asarray(values, dtype=float).ravel()
    if arr.size == 0:
        raise ValueError("values must contain at least one element")
    if not np.all(np.isfinite(arr)):
        raise ValueError("values must all be finite numbers")
    return arr


def median(values: Any) -> float:
    """Sample median (50% breakdown point)."""
    return float(np.median(_as_array(values)))


def trimmed_mean(values: Any, trim: float = 0.1) -> float:
    """Symmetric trimmed mean: drop ``trim`` fraction from each tail, average rest.

    ``trim`` is clamped to ``[0, 0.5)``. With ``trim=0`` this is the plain mean;
    as ``trim`` → 0.5 it approaches the median. If trimming would remove every
    element (tiny samples) we fall back to the median so a value is always
    returned.
    """
    arr = np.sort(_as_array(values))
    n = arr.size
    t = float(min(max(trim, 0.0), 0.499))
    k = int(np.floor(n * t))
    if 2 * k >= n:
        return float(np.median(arr))
    kept = arr[k : n - k]
    return float(np.mean(kept))


def mad(values: Any, center: float | None = None) -> float:
    """Median absolute deviation, scaled to be a consistent σ estimate (×1.4826)."""
    arr = _as_array(values)
    c = float(np.median(arr)) if center is None else center
    return float(1.4826 * np.median(np.abs(arr - c)))


def biweight_location(
    values: Any, c: float = BIWEIGHT_C, max_iter: int = 50, tol: float = 1e-9
) -> float:
    """Tukey biweight location M-estimator via iteratively reweighted least squares.

    Weights ``w_i = (1 - u_i^2)^2`` for ``|u_i| < 1`` else ``0``, where
    ``u_i = (x_i - T) / (c * MAD)``. Redescending → far outliers contribute
    nothing. Seeded at the median; converges in a handful of iterations.
    """
    arr = _as_array(values)
    if arr.size == 1:
        return float(arr[0])

    T = float(np.median(arr))
    s = mad(arr, center=T)
    if s < _EPS:
        # No spread (or all-but-ties): the median is already the answer.
        return T

    denom = c * s
    for _ in range(max_iter):
        u = (arr - T) / denom
        mask = np.abs(u) < 1.0
        if not np.any(mask):
            # Everything flagged as an outlier vs. current centre → keep median.
            return float(np.median(arr))
        w = np.where(mask, (1.0 - u**2) ** 2, 0.0)
        wsum = float(np.sum(w))
        if wsum < _EPS:
            return float(np.median(arr))
        T_new = float(np.sum(w * arr) / wsum)
        if abs(T_new - T) <= tol * (abs(T) + tol):
            T = T_new
            break
        T = T_new
    return T


def degroot_consensus(
    values: Any, max_iter: int = 1000, tol: float = 1e-9
) -> dict[str, Any]:
    """Simulate DeGroot opinion dynamics on the complete graph.

    The averaging matrix is ``W = (1/n) · 11ᵀ`` (row-stochastic, every agent
    weights everyone equally). We iterate ``x ← W x`` — implemented as the cheap
    broadcast of the current mean — until the opinion spread
    ``max(x) - min(x)`` drops below ``tol``. Returns the converged value (which
    provably equals the arithmetic mean) and the number of iterations taken.
    """
    x = _as_array(values).copy()
    n = x.size
    if n == 1:
        return {"converged_value": float(x[0]), "iterations": 0}

    iterations = 0
    for _ in range(max_iter):
        spread = float(np.max(x) - np.min(x))
        if spread <= tol:
            break
        # x_{k+1} = W x_k ; for the complete graph each new coordinate is the mean.
        x = np.full(n, float(np.mean(x)))
        iterations += 1
    return {"converged_value": float(np.mean(x)), "iterations": iterations}


def aggregate(values: Any, trim: float = 0.1) -> dict[str, Any]:
    """Full robust-consensus aggregate used by the capability handler.

    Returns the sample size and four location estimators (median, trimmed mean,
    Tukey biweight, DeGroot-converged value) plus the consensus iteration count.
    """
    arr = _as_array(values)
    dg = degroot_consensus(arr)
    return {
        "n": int(arr.size),
        "median": median(arr),
        "trimmed_mean": trimmed_mean(arr, trim),
        "biweight": biweight_location(arr),
        "converged_value": dg["converged_value"],
        "iterations": dg["iterations"],
    }
