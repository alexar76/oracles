"""Gaussian-Process regression — posterior uncertainty + Expected-Improvement active learning.

A Gaussian process places a distribution over *functions*: any finite set of points
is jointly Gaussian, fully specified by a mean (taken 0 here) and a covariance kernel
``k(x, x')``. We use the RBF / squared-exponential kernel

    k(x, x') = sigma_f^2 · exp(-||x - x'||^2 / (2 · l^2))

with signal variance ``sigma_f^2`` (vertical scale of the function) and length-scale
``l`` (how far you can extrapolate before correlation decays). Observations carry i.i.d.
Gaussian noise of variance ``sigma_n^2``.

Given training inputs ``X`` (n×d) with targets ``y`` (n), the noisy training covariance
is ``K = k(X, X) + sigma_n^2 · I``. Conditioning the joint prior on the data gives the
**posterior** at query points ``Xq``:

    mean(Xq) = Kqx · K^{-1} · y
    cov(Xq)  = k(Xq, Xq) - Kqx · K^{-1} · Kqx^T

We never invert ``K``. Following Rasmussen & Williams (Algorithm 2.1) we Cholesky-factor
``K = L L^T`` (``L`` lower-triangular), solve ``alpha = K^{-1} y`` by two triangular
solves, and obtain the predictive variance from ``v = L^{-1} Kqx^T`` as
``diag(Kqq) - sum(v*v, axis=0)`` — numerically stable and O(n^3) once, O(n) per query.
scipy is unavailable, so everything rides on ``numpy.linalg`` (cholesky, solve_triangular
emulated via ``solve`` against the triangular factor) and ``math.erf`` for the Gaussian
CDF used by Expected Improvement.

The posterior variance is the *principled* uncertainty an agent needs for exploration:
it is exactly ``sigma_n^2`` at a noiseless-limit observation and rises to the prior
``sigma_f^2`` far from any data. Expected Improvement turns that posterior into the next
best experiment to run — a calibrated replacement for hand-tuned UCB / bandit heuristics.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np

# ---- DoS clamps. The protocol layer does NOT validate input_schema, so a caller can
# ---- post arbitrarily large X / query arrays. The GP is O(n^3) in observations and
# ---- O(n^2 · m) in query points, so we cap both hard before touching numpy.
MAX_OBS = 200            # training points (Cholesky is n^3)
MAX_QUERY = 2048         # query / candidate points (one posterior sweep)
MAX_DIM = 64             # input dimensionality

# ---- sane hyperparameter defaults (used when the caller omits them) ----
DEFAULT_SIGNAL_VAR = 1.0     # sigma_f^2 — prior function variance
DEFAULT_NOISE_VAR = 1e-6     # sigma_n^2 — observation noise (also a jitter floor)
JITTER = 1e-9                # added to the diagonal for Cholesky stability
DEFAULT_XI = 0.01            # EI exploration margin


# --------------------------------------------------------------------------- #
#  standard-normal CDF / PDF via math.erf (no scipy)
# --------------------------------------------------------------------------- #
def _norm_cdf(z: np.ndarray) -> np.ndarray:
    """Phi(z) = 0.5 · (1 + erf(z / sqrt(2))) — vectorised over a numpy array."""
    out = np.empty_like(z, dtype=np.float64)
    flat = z.reshape(-1)
    res = out.reshape(-1)
    inv_sqrt2 = 1.0 / math.sqrt(2.0)
    for i in range(flat.shape[0]):
        res[i] = 0.5 * (1.0 + math.erf(float(flat[i]) * inv_sqrt2))
    return out


def _norm_pdf(z: np.ndarray) -> np.ndarray:
    """phi(z) = exp(-z^2 / 2) / sqrt(2·pi)."""
    return np.exp(-0.5 * z * z) / math.sqrt(2.0 * math.pi)


# --------------------------------------------------------------------------- #
#  input coercion / validation
# --------------------------------------------------------------------------- #
def _as_matrix(name: str, value: Any, *, max_rows: int) -> np.ndarray:
    """Coerce ``value`` to a finite float (rows × d) matrix, validating + clamping."""
    if value is None:
        raise ValueError(f"missing '{name}'")
    arr = np.asarray(value, dtype=np.float64)
    if arr.ndim == 1:
        arr = arr.reshape(1, -1)
    if arr.ndim != 2:
        raise ValueError(f"'{name}' must be a 2D array of points (rows × dim)")
    if arr.shape[0] == 0:
        raise ValueError(f"'{name}' must contain at least one point")
    if arr.shape[0] > max_rows:
        raise ValueError(f"'{name}' exceeds the maximum of {max_rows} points")
    if arr.shape[1] == 0:
        raise ValueError(f"'{name}' points must have at least one dimension")
    if arr.shape[1] > MAX_DIM:
        raise ValueError(f"'{name}' dimensionality exceeds {MAX_DIM}")
    if not np.all(np.isfinite(arr)):
        raise ValueError(f"'{name}' must be finite (no NaN / inf)")
    return arr


def _as_vector(name: str, value: Any, n: int) -> np.ndarray:
    if value is None:
        raise ValueError(f"missing '{name}'")
    arr = np.asarray(value, dtype=np.float64).reshape(-1)
    if arr.shape[0] != n:
        raise ValueError(f"'{name}' length {arr.shape[0]} != number of points {n}")
    if not np.all(np.isfinite(arr)):
        raise ValueError(f"'{name}' must be finite (no NaN / inf)")
    return arr


def resolve_hyperparams(X: np.ndarray, y: np.ndarray, hp: dict[str, Any] | None) -> dict[str, float]:
    """Validate caller hyperparams; fill missing ones with sane / heuristic defaults.

    ``length_scale`` defaults to a cheap median-pairwise-distance heuristic (a robust,
    scale-aware estimate of how far correlations should reach), capped to stay positive.
    ``signal_var`` defaults to the sample variance of ``y`` (the function's vertical
    scale), and ``noise_var`` to a tiny floor so the kernel stays positive-definite.
    """
    hp = hp or {}

    def _pos(key: str, default: float) -> float:
        if key in hp and hp[key] is not None:
            v = float(hp[key])
            if not math.isfinite(v) or v <= 0.0:
                raise ValueError(f"hyperparam '{key}' must be a positive finite number")
            return v
        return default

    # length-scale heuristic: median nonzero pairwise distance over training inputs.
    if "length_scale" in hp and hp["length_scale"] is not None:
        length_scale = _pos("length_scale", 1.0)
    else:
        length_scale = _median_distance_heuristic(X)

    # signal variance: sample variance of y (clamped above 0), else the prior default.
    if "signal_var" in hp and hp["signal_var"] is not None:
        signal_var = _pos("signal_var", DEFAULT_SIGNAL_VAR)
    else:
        yv = float(np.var(y)) if y.shape[0] > 1 else 0.0
        signal_var = yv if yv > 1e-12 else DEFAULT_SIGNAL_VAR

    noise_var = _pos("noise_var", DEFAULT_NOISE_VAR)
    return {"length_scale": length_scale, "signal_var": signal_var, "noise_var": noise_var}


def _median_distance_heuristic(X: np.ndarray) -> float:
    n = X.shape[0]
    if n < 2:
        return 1.0
    d2 = _sq_dists(X, X)
    iu = np.triu_indices(n, k=1)
    dists = np.sqrt(np.maximum(d2[iu], 0.0))
    nz = dists[dists > 1e-12]
    med = float(np.median(nz)) if nz.size else 1.0
    return med if med > 1e-9 else 1.0


# --------------------------------------------------------------------------- #
#  RBF kernel
# --------------------------------------------------------------------------- #
def _sq_dists(A: np.ndarray, B: np.ndarray) -> np.ndarray:
    """Pairwise squared Euclidean distances ||a_i - b_j||^2 (rows of A × rows of B)."""
    a2 = np.sum(A * A, axis=1)[:, None]
    b2 = np.sum(B * B, axis=1)[None, :]
    d2 = a2 + b2 - 2.0 * (A @ B.T)
    return np.maximum(d2, 0.0)


def rbf_kernel(A: np.ndarray, B: np.ndarray, length_scale: float, signal_var: float) -> np.ndarray:
    """k(a, b) = sigma_f^2 · exp(-||a - b||^2 / (2 · l^2))."""
    d2 = _sq_dists(A, B)
    return signal_var * np.exp(-0.5 * d2 / (length_scale * length_scale))


# --------------------------------------------------------------------------- #
#  posterior (Rasmussen & Williams, Algorithm 2.1)
# --------------------------------------------------------------------------- #
class Posterior:
    """A fitted GP: holds the Cholesky factor + alpha so queries are cheap."""

    def __init__(self, X: np.ndarray, y: np.ndarray, hp: dict[str, float]):
        self.X = X
        self.y = y
        self.length_scale = hp["length_scale"]
        self.signal_var = hp["signal_var"]
        self.noise_var = hp["noise_var"]
        n = X.shape[0]
        K = rbf_kernel(X, X, self.length_scale, self.signal_var)
        K[np.diag_indices(n)] += self.noise_var + JITTER
        # K = L L^T ; alpha = K^{-1} y via two triangular solves against L, L^T.
        self.L = np.linalg.cholesky(K)
        self.alpha = np.linalg.solve(self.L.T, np.linalg.solve(self.L, y))

    def predict(self, Xq: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Posterior mean and variance (clamped >= 0) at the query points ``Xq``."""
        Kqx = rbf_kernel(Xq, self.X, self.length_scale, self.signal_var)  # (m, n)
        mean = Kqx @ self.alpha
        # v = L^{-1} Kqx^T ; var_i = k(x_i, x_i) - ||v_i||^2.
        v = np.linalg.solve(self.L, Kqx.T)  # (n, m)
        prior_var = self.signal_var  # k(x, x) = sigma_f^2 for the RBF kernel
        var = prior_var - np.sum(v * v, axis=0)
        var = np.maximum(var, 0.0)
        return mean, var


def fit(X: np.ndarray, y: np.ndarray, hp: dict[str, Any] | None = None) -> Posterior:
    resolved = resolve_hyperparams(X, y, hp)
    return Posterior(X, y, resolved)


# --------------------------------------------------------------------------- #
#  capability cores
# --------------------------------------------------------------------------- #
def field(d: dict[str, Any]) -> dict[str, Any]:
    """GP posterior mean + variance over a query field (the 'breathing fog' surface)."""
    X = _as_matrix("X", d.get("X"), max_rows=MAX_OBS)
    y = _as_vector("y", d.get("y"), X.shape[0])
    Xq = _as_matrix("query", d.get("query"), max_rows=MAX_QUERY)
    if Xq.shape[1] != X.shape[1]:
        raise ValueError(f"query dim {Xq.shape[1]} != training dim {X.shape[1]}")

    post = fit(X, y, d.get("hyperparams"))
    mean, var = post.predict(Xq)
    std = np.sqrt(var)
    return {
        "mean": [float(x) for x in mean],
        "var": [float(x) for x in var],
        "std": [float(x) for x in std],
        "hyperparams": {
            "length_scale": post.length_scale,
            "signal_var": post.signal_var,
            "noise_var": post.noise_var,
        },
        "n": int(X.shape[0]),
        "d": int(X.shape[1]),
    }


def _candidate_points(d: dict[str, Any], dim: int) -> np.ndarray:
    """Resolve candidates: an explicit list, or a bounds-box swept by a grid."""
    cand = d.get("candidates")
    if cand is not None:
        return _as_matrix("candidates", cand, max_rows=MAX_QUERY)
    bounds = d.get("bounds")
    if bounds is not None:
        b = np.asarray(bounds, dtype=np.float64)
        if b.ndim != 2 or b.shape[1] != 2:
            raise ValueError("'bounds' must be a list of [lo, hi] pairs, one per dimension")
        if b.shape[0] != dim:
            raise ValueError(f"'bounds' has {b.shape[0]} dims != training dim {dim}")
        if not np.all(np.isfinite(b)) or np.any(b[:, 1] < b[:, 0]):
            raise ValueError("'bounds' must be finite with hi >= lo")
        grid = int(d.get("grid", 64))
        if grid < 2:
            raise ValueError("'grid' must be >= 2")
        # Per-axis grid points; cap the total product to MAX_QUERY to stay bounded.
        per_axis = max(2, int(round(MAX_QUERY ** (1.0 / dim))))
        grid = min(grid, per_axis)
        axes = [np.linspace(b[k, 0], b[k, 1], grid) for k in range(dim)]
        mesh = np.meshgrid(*axes, indexing="ij")
        pts = np.stack([m.reshape(-1) for m in mesh], axis=1)
        if pts.shape[0] > MAX_QUERY:
            pts = pts[:MAX_QUERY]
        return pts
    raise ValueError("provide either 'candidates' or 'bounds' (+ optional 'grid')")


def suggest(d: dict[str, Any]) -> dict[str, Any]:
    """Best next experiment by Expected Improvement over candidate points.

    EI(x) = (mu - f_best - xi) · Phi(z) + std · phi(z),  z = (mu - f_best - xi) / std.
    For a minimisation goal we negate y, run the maximisation form, and report the
    acquisition on the original scale. The argmax candidate is the suggested next point.
    """
    X = _as_matrix("X", d.get("X"), max_rows=MAX_OBS)
    y = _as_vector("y", d.get("y"), X.shape[0])
    goal = str(d.get("goal", "max")).lower()
    if goal not in ("max", "min"):
        raise ValueError("'goal' must be 'max' or 'min'")
    xi = float(d.get("xi", DEFAULT_XI))
    if not math.isfinite(xi) or xi < 0.0:
        raise ValueError("'xi' must be a non-negative finite number")

    Xc = _candidate_points(d, X.shape[1])

    # Minimisation: negate so the same maximisation-EI applies; f_best is the running best.
    sign = -1.0 if goal == "min" else 1.0
    y_max = sign * y
    post = fit(X, y_max, d.get("hyperparams"))
    mean, var = post.predict(Xc)
    std = np.sqrt(var)
    f_best = float(np.max(y_max))

    # EI with a std>0 guard: where std == 0 the posterior is certain, so EI is 0.
    imp = mean - f_best - xi
    safe = std > 1e-12
    z = np.zeros_like(mean)
    z[safe] = imp[safe] / std[safe]
    ei = np.zeros_like(mean)
    ei[safe] = imp[safe] * _norm_cdf(z[safe]) + std[safe] * _norm_pdf(z[safe])
    ei = np.maximum(ei, 0.0)

    idx = int(np.argmax(ei))
    return {
        "best": [float(x) for x in Xc[idx]],
        "ei": float(ei[idx]),
        "acquisition": [float(x) for x in ei],
        "index": idx,
        "goal": goal,
        "f_best": float(sign * f_best),
        "n_candidates": int(Xc.shape[0]),
        "hyperparams": {
            "length_scale": post.length_scale,
            "signal_var": post.signal_var,
            "noise_var": post.noise_var,
        },
    }


def verify(d: dict[str, Any]) -> dict[str, Any]:
    """Trustless replay: recompute the posterior at the query points and check claims.

    The caller hands back the (X, y, query, hyperparams) plus the mean / var it was
    given; we refit the GP and compare. Cheap, needs no trust in the original oracle.
    """
    X = _as_matrix("X", d.get("X"), max_rows=MAX_OBS)
    y = _as_vector("y", d.get("y"), X.shape[0])
    Xq = _as_matrix("query", d.get("query"), max_rows=MAX_QUERY)
    if Xq.shape[1] != X.shape[1]:
        raise ValueError(f"query dim {Xq.shape[1]} != training dim {X.shape[1]}")

    post = fit(X, y, d.get("hyperparams"))
    mean, var = post.predict(Xq)

    tol = float(d.get("tol", 1e-6))
    max_err = 0.0
    valid = True

    claimed_mean = d.get("claimed_mean")
    if claimed_mean is not None:
        cm = np.asarray(claimed_mean, dtype=np.float64).reshape(-1)
        if cm.shape[0] != mean.shape[0]:
            valid = False
        else:
            err = float(np.max(np.abs(cm - mean)))
            max_err = max(max_err, err)
            if err > tol:
                valid = False

    claimed_var = d.get("claimed_var")
    if claimed_var is not None:
        cv = np.asarray(claimed_var, dtype=np.float64).reshape(-1)
        if cv.shape[0] != var.shape[0]:
            valid = False
        else:
            err = float(np.max(np.abs(cv - var)))
            max_err = max(max_err, err)
            if err > tol:
                valid = False

    if claimed_mean is None and claimed_var is None:
        raise ValueError("provide 'claimed_mean' and/or 'claimed_var' to verify")

    return {
        "valid": bool(valid),
        "recomputed_mean": [float(x) for x in mean],
        "recomputed_var": [float(x) for x in var],
        "max_abs_err": float(max_err),
        "tol": tol,
    }
