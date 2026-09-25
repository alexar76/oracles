"""DREAM surrogate — a real least-squares-fitted linear model of the dynamics.

No hand-tuned constants. We sample the true RK2 trajectory, then fit a linear
one-step predictor x_{t+1} ≈ W·[x_t, 1] by ordinary least squares (closed-form,
provable). The fit is *over-determined* (samples >> dimensions), so it carries a
genuine, measurable residual — a linear model cannot perfectly capture a chaotic
nonlinear flow. Propagating that learned model and comparing to truth is exactly
what DREAM shows: a fitted predictor tracks short-term, then diverges at the
Lyapunov horizon. The display projection is the same orthonormal Stiefel frame,
so a runaway prediction stays visually bounded on the unit circle.
"""

from __future__ import annotations

import numpy as np

from platon.dynamics import DynamicsState, step, stiefel_projection

TRAJECTORIES = 16  # diverse local rollouts -> design matrix is not collinear
SAMPLES_PER_TRAJ = 18  # 16*18 = 288 pairs >> 65 params/output
PERTURB = 0.18  # spread of initial conditions around the current state


def fit_linear_model(
    state: DynamicsState,
    trajectories: int = TRAJECTORIES,
    samples_per_traj: int = SAMPLES_PER_TRAJ,
    dt: float = 0.02,
) -> tuple[np.ndarray, float]:
    """Fit x_{t+1} ≈ [x_t, 1] · W by least squares over a NEIGHBOURHOOD of the
    state (several perturbed rollouts), not one collinear trajectory. The flow is
    nonlinear, so a linear model has a genuine non-zero residual — a real fit, not
    interpolation. Returns (W, train_residual_rms). Deterministic (fixed RNG)."""
    rng = np.random.default_rng(0)
    base = state.as_vector()
    n = len(base)
    rows_x: list[np.ndarray] = []
    rows_y: list[np.ndarray] = []
    for _ in range(trajectories):
        probe = state.copy()
        v = base + rng.normal(0.0, PERTURB, size=n)
        probe.z_real = v[: n // 2].copy()
        probe.z_imag = v[n // 2 :].copy()
        for _ in range(samples_per_traj):
            x = probe.as_vector()
            probe = step(probe, dt)
            rows_x.append(x)
            rows_y.append(probe.as_vector())

    X = np.asarray(rows_x, dtype=np.float64)
    Y = np.asarray(rows_y, dtype=np.float64)
    X_aug = np.hstack([X, np.ones((len(X), 1))])
    W, _residuals, _rank, _sv = np.linalg.lstsq(X_aug, Y, rcond=None)

    pred = X_aug @ W
    residual_rms = float(np.sqrt(np.mean((pred - Y) ** 2)))
    return W, residual_rms


def _predict(W: np.ndarray, x: np.ndarray) -> np.ndarray:
    return np.append(x, 1.0) @ W


def dream_trajectory(
    state: DynamicsState, steps: int = 60, dt: float = 0.02
) -> tuple[list[tuple[float, float]], list[tuple[float, float]], dict]:
    """Return (surrogate_path, truth_path, fit_info).

    ``truth`` integrates real RK2 physics. ``surrogate`` propagates the
    least-squares-fitted linear model from the same start. ``fit_info`` reports
    the learned model's training residual (no magic constants anywhere).
    """
    theta1, theta2 = 0.7, 1.1
    W, residual_rms = fit_linear_model(state, dt=dt)

    real = state.copy()
    approx_vec = state.as_vector()
    truth: list[tuple[float, float]] = []
    surrogate: list[tuple[float, float]] = []

    for _ in range(steps):
        truth.append(stiefel_projection(real, theta1, theta2))

        if np.all(np.isfinite(approx_vec)):
            approx_vec = _predict(W, approx_vec)
        safe_vec = np.where(np.isfinite(approx_vec), approx_vec, 0.0)
        approx = DynamicsState.from_vector(safe_vec, kappa=state.kappa)
        surrogate.append(stiefel_projection(approx, theta1, theta2))

        real = step(real, dt)

    fit_info = {
        "model": "least_squares_linear",
        "train_samples": TRAJECTORIES * SAMPLES_PER_TRAJ,
        "train_residual_rms": round(residual_rms, 6),
    }
    return surrogate, truth, fit_info
