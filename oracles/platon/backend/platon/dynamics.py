"""32D coupled Stuart-Landau / Kuramoto dynamics."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

import numpy as np

N = 32


@dataclass
class DynamicsState:
    """Complex amplitudes z_i = r_i * exp(i * theta_i)."""

    z_real: np.ndarray = field(default_factory=lambda: np.zeros(N, dtype=np.float64))
    z_imag: np.ndarray = field(default_factory=lambda: np.zeros(N, dtype=np.float64))
    kappa: float = 0.4
    omega: np.ndarray = field(
        default_factory=lambda: np.linspace(0.8, 2.4, N, dtype=np.float64)
    )
    steering_bias: np.ndarray = field(
        default_factory=lambda: np.zeros(N, dtype=np.float64)
    )

    def as_vector(self) -> np.ndarray:
        return np.concatenate([self.z_real, self.z_imag])

    @classmethod
    def from_vector(cls, v: np.ndarray, kappa: float = 0.4) -> DynamicsState:
        state = cls(kappa=kappa)
        state.z_real = v[:N].copy()
        state.z_imag = v[N:].copy()
        return state

    def copy(self) -> DynamicsState:
        """Full clone preserving kappa, omega and steering_bias."""
        clone = DynamicsState(kappa=self.kappa)
        clone.z_real = self.z_real.copy()
        clone.z_imag = self.z_imag.copy()
        clone.omega = self.omega.copy()
        clone.steering_bias = self.steering_bias.copy()
        return clone

    def phases(self) -> np.ndarray:
        return np.arctan2(self.z_imag, self.z_real)

    def amplitudes(self) -> np.ndarray:
        return np.hypot(self.z_real, self.z_imag)

    def order_parameter(self) -> float:
        phases = self.phases()
        return float(np.abs(np.mean(np.exp(1j * phases))))

    def reset_random(self, seed: int = 42) -> None:
        rng = np.random.default_rng(seed)
        r = rng.uniform(0.2, 0.9, N)
        theta = rng.uniform(0, 2 * np.pi, N)
        self.z_real = r * np.cos(theta)
        self.z_imag = r * np.sin(theta)


def stiefel_projection(
    state: DynamicsState, theta1: float, theta2: float
) -> tuple[float, float]:
    """Project the 64D state onto 2D via a genuine orthonormal 2-frame on the
    Stiefel manifold St(64, 2).

    Two angle-seeded direction vectors are Gram-Schmidt orthonormalized into a
    frame U = [u1, u2] with Uᵀ U = I, then x = <v, u1>, y = <v, u2>. The angles
    (theta1, theta2) sweep the frame across the manifold, so rotating them shows
    genuinely different orthogonal shadows of the same high-D state.
    """
    v = state.as_vector()
    n = len(v)
    idx = np.arange(n, dtype=np.float64)
    r1 = np.cos(theta1 + idx * (theta2 + 0.5) * np.pi / n)
    r2 = np.sin(theta2 + idx * (theta1 + 0.5) * np.pi / n)

    # Gram-Schmidt -> orthonormal frame [u1, u2].
    u1 = r1 / max(float(np.linalg.norm(r1)), 1e-12)
    r2 = r2 - float(np.dot(r2, u1)) * u1
    norm2 = float(np.linalg.norm(r2))
    if norm2 < 1e-9:  # degenerate angles: take any direction orthogonal to u1
        alt = np.roll(u1, 1)
        r2 = alt - float(np.dot(alt, u1)) * u1
        norm2 = max(float(np.linalg.norm(r2)), 1e-12)
    u2 = r2 / norm2

    x = float(np.dot(v, u1))
    y = float(np.dot(v, u2))
    scale = max(np.hypot(x, y), 1e-9)
    return x / scale, y / scale


def lyapunov_proxy(state: DynamicsState, dt: float = 0.02) -> float:
    """Finite-time divergence proxy via perturbed step.

    Both trajectories evolve under the *same* parameters (omega, steering_bias,
    kappa); only the initial condition differs by 1e-6, so the measured growth
    is genuine sensitivity, not a parameter mismatch.
    """
    perturbed = state.copy()
    perturbed.z_real[0] += 1e-6

    s1 = step(perturbed, dt)
    s0 = step(state, dt)
    delta = np.linalg.norm(s1.as_vector() - s0.as_vector())
    return float(np.log(max(delta, 1e-18) / 1e-6) / dt)


def step(state: DynamicsState, dt: float) -> DynamicsState:
    """RK2 integration of coupled Stuart-Landau oscillators."""
    def deriv(s: DynamicsState) -> tuple[np.ndarray, np.ndarray]:
        r = s.amplitudes()
        theta = s.phases()
        mean_phase = np.arctan2(
            np.mean(np.sin(theta)), np.mean(np.cos(theta))
        )
        dtheta = s.omega + s.steering_bias + s.kappa * np.sin(mean_phase - theta)
        dr = r * (1.0 - r**2)
        dz_r = dr * np.cos(theta) - r * np.sin(theta) * dtheta
        dz_i = dr * np.sin(theta) + r * np.cos(theta) * dtheta
        return dz_r, dz_i

    k1r, k1i = deriv(state)
    # Midpoint MUST carry omega + steering_bias, otherwise the k2 corrector
    # (which alone determines the output of midpoint RK2) is computed with the
    # wrong frequencies and zero steering — silently dropping the steering.
    mid = state.copy()
    mid.z_real = state.z_real + 0.5 * dt * k1r
    mid.z_imag = state.z_imag + 0.5 * dt * k1i
    k2r, k2i = deriv(mid)

    out = state.copy()
    out.z_real = state.z_real + dt * k2r
    out.z_imag = state.z_imag + dt * k2i
    return out


def steer_from_text(text: str) -> tuple[float, np.ndarray]:
    """Map natural language to kappa and per-oscillator frequency bias."""
    digest = hashlib.sha256(text.strip().lower().encode()).digest()
    kappa = 0.15 + (digest[0] / 255.0) * 1.2
    bias = np.array(
        [(digest[i % len(digest)] / 127.5 - 1.0) * 0.35 for i in range(N)],
        dtype=np.float64,
    )
    return kappa, bias


def detect_event(prev_r: float, curr_r: float, lyap: float) -> str | None:
    if prev_r < 0.35 and curr_r >= 0.55:
        return "chimera_birth"
    if prev_r >= 0.55 and curr_r < 0.35:
        return "chimera_death"
    if lyap > 2.5:
        return "chaos_threshold"
    if curr_r > 0.85:
        return "full_synchronization"
    return None
