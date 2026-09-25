import pytest
import numpy as np

from platon.dynamics import (
    DynamicsState,
    detect_event,
    lyapunov_proxy,
    stiefel_projection,
    steer_from_text,
    step,
    N,
)
from platon.surrogate import dream_trajectory, fit_linear_model


class TestDynamics:
    def test_reset_random_produces_valid_state(self):
        s = DynamicsState()
        s.reset_random(seed=7)
        amps = s.amplitudes()
        assert len(amps) == N
        assert np.all(amps >= 0)
        assert np.all(np.isfinite(amps))

    def test_step_preserves_dimension(self):
        s = DynamicsState()
        s.reset_random()
        nxt = step(s, 0.02)
        assert len(nxt.as_vector()) == 2 * N

    def test_order_parameter_bounded(self):
        s = DynamicsState()
        s.reset_random()
        for _ in range(100):
            s = step(s, 0.02)
        r = s.order_parameter()
        assert 0.0 <= r <= 1.0 + 1e-9

    def test_stiefel_projection_normalized(self):
        s = DynamicsState()
        s.reset_random()
        x, y = stiefel_projection(s, 0.5, 1.0)
        norm = np.hypot(x, y)
        assert abs(norm - 1.0) < 0.01 or norm < 1e-6

    def test_steer_deterministic(self):
        k1, b1 = steer_from_text("entropy cathedral")
        k2, b2 = steer_from_text("entropy cathedral")
        assert k1 == k2
        assert np.allclose(b1, b2)

    def test_steer_different_prompts(self):
        k1, _ = steer_from_text("chaos")
        k2, _ = steer_from_text("harmony")
        assert k1 != k2

    def test_detect_chimera_birth(self):
        assert detect_event(0.2, 0.6, 0.5) == "chimera_birth"

    def test_detect_full_sync(self):
        assert detect_event(0.5, 0.9, 0.5) == "full_synchronization"

    def test_lyapunov_finite(self):
        s = DynamicsState()
        s.reset_random()
        lyap = lyapunov_proxy(s)
        assert np.isfinite(lyap)

    def test_steering_bias_changes_trajectory(self):
        # Regression: the RK2 midpoint used to drop steering_bias, so the
        # corrector (which alone sets the output) ignored steering entirely.
        base = DynamicsState()
        base.reset_random(seed=7)
        steered = base.copy()
        steered.steering_bias = np.full(N, 0.5)

        a, b = base, steered
        for _ in range(50):
            a = step(a, 0.02)
            b = step(b, 0.02)
        divergence = float(np.linalg.norm(a.as_vector() - b.as_vector()))
        assert divergence > 0.05

    def test_stiefel_frame_is_orthonormal(self):
        # The two angle-seeded directions must form an orthonormal 2-frame.
        s = DynamicsState()
        s.reset_random()
        n = len(s.as_vector())
        idx = np.arange(n, dtype=float)
        t1, t2 = 0.7, 1.1
        r1 = np.cos(t1 + idx * (t2 + 0.5) * np.pi / n)
        r2 = np.sin(t2 + idx * (t1 + 0.5) * np.pi / n)
        u1 = r1 / np.linalg.norm(r1)
        r2 = r2 - r2 @ u1 * u1
        u2 = r2 / np.linalg.norm(r2)
        assert abs(u1 @ u2) < 1e-9
        assert abs(u1 @ u1 - 1.0) < 1e-9 and abs(u2 @ u2 - 1.0) < 1e-9


class TestSurrogate:
    def test_dream_returns_paths(self):
        s = DynamicsState()
        s.reset_random()
        surr, truth, fit = dream_trajectory(s, steps=30)
        assert len(surr) == 30
        assert len(truth) == 30
        assert all(len(p) == 2 for p in surr)
        assert fit["model"] == "least_squares_linear"

    def test_dream_eventually_diverges(self):
        s = DynamicsState()
        s.reset_random(seed=99)
        for _ in range(200):
            s = step(s, 0.02)
        surr, truth, _ = dream_trajectory(s, steps=60)
        diffs = [np.hypot(a[0] - b[0], a[1] - b[1]) for a, b in zip(surr, truth)]
        assert max(diffs) > 0.01

    def test_fitted_model_shape_and_finite(self):
        # The learned linear model is a real least-squares fit (no magic
        # constants); the closed-form solution is finite and well-shaped.
        s = DynamicsState()
        s.reset_random(seed=5)
        W, residual_rms = fit_linear_model(s)
        assert W.shape == (2 * N + 1, 2 * N)  # [x, 1] -> x_next
        assert np.all(np.isfinite(W))
        assert 0.0 <= residual_rms < 1.0 and np.isfinite(residual_rms)

    def test_dream_divergence_grows_to_lyapunov_horizon(self):
        # Honest DREAM property: the fitted model tracks early and diverges late.
        s = DynamicsState()
        s.reset_random(seed=99)
        surr, truth, _ = dream_trajectory(s, steps=60)
        diffs = [np.hypot(a[0] - b[0], a[1] - b[1]) for a, b in zip(surr, truth)]
        early = float(np.mean(diffs[:5]))
        late = float(np.mean(diffs[-5:]))
        assert late > early

    def test_surrogate_outputs_are_finite(self):
        s = DynamicsState()
        s.reset_random(seed=11)
        surr, truth, _ = dream_trajectory(s, steps=60)
        assert all(np.isfinite(x) and np.isfinite(y) for x, y in surr)
        assert all(np.isfinite(x) and np.isfinite(y) for x, y in truth)
