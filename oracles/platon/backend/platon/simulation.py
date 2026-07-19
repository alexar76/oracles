"""Global simulation engine and event bus."""

from __future__ import annotations

import asyncio
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from platon.config import settings
from platon.dynamics import (
    DynamicsState,
    detect_event,
    lyapunov_proxy,
    stiefel_projection,
    steer_from_text,
    step,
)
from platon.oracle import generate_witness
from platon.surrogate import dream_trajectory

# Window (in ticks) over which effective dimensionality (top-3 PCA energy) is
# measured. A single state is rank-1; phases need a few time units to spread for
# the metric to distinguish synchronized (low-dim) from chaotic (high-dim) motion.
PCA_WINDOW = 256


@dataclass
class WitnessRecord:
    event: str
    text: str
    source: str
    model: str | None
    timestamp: float
    telemetry: dict[str, Any]


@dataclass
class SimulationEngine:
    state: DynamicsState = field(default_factory=DynamicsState)
    projection_theta1: float = 0.7
    projection_theta2: float = 1.1
    tick: int = 0
    viewers: int = 0
    witnesses: deque[WitnessRecord] = field(default_factory=lambda: deque(maxlen=200))
    activity: deque[dict[str, Any]] = field(default_factory=lambda: deque(maxlen=500))
    _prev_order: float = 0.0
    _running: bool = False
    _pca_cache: tuple[int, float] | None = None
    _state_window: deque = field(default_factory=lambda: deque(maxlen=PCA_WINDOW))

    def __post_init__(self) -> None:
        self.state.reset_random()
        self._state_window.append(self.state.as_vector())

    def telemetry(self) -> dict[str, Any]:
        r = self.state.order_parameter()
        lyap = lyapunov_proxy(self.state)
        px, py = stiefel_projection(
            self.state, self.projection_theta1, self.projection_theta2
        )
        amps = self.state.amplitudes()
        phases = self.state.phases()
        return {
            "tick": self.tick,
            "kappa": round(self.state.kappa, 4),
            "order_parameter": round(r, 4),
            "lyapunov": round(lyap, 4),
            "projection": {"x": round(px, 4), "y": round(py, 4)},
            "viewers": self.viewers,
            "oscillators": {
                "amplitudes": [round(float(a), 4) for a in amps],
                "phases": [round(float(p), 4) for p in phases],
            },
            "pca_energy_3": round(self._pca_energy(), 4),
            "projection_angles": {
                "theta1": round(self.projection_theta1, 4),
                "theta2": round(self.projection_theta2, 4),
            },
        }

    def _pca_energy(self) -> float:
        """Fraction of recent-trajectory variance captured by its top 3 PCA modes.

        A single state is rank-1, so PCA must run over a *time window*. We use the
        real recent trajectory (``_state_window``, filled each tick); when it is
        not yet warm (standalone/test calls with no running loop) we roll a copy
        of the current state forward to fill a probe window. Synchronized motion
        is low-dimensional (ratio -> 1); chaotic motion spreads energy across many
        modes (ratio drops). Cached per tick — telemetry() runs many times a tick.
        """
        if self._pca_cache is not None and self._pca_cache[0] == self.tick:
            return self._pca_cache[1]

        rows = list(self._state_window)
        if len(rows) < 32:
            probe = self.state.copy()
            dt = 1.0 / settings.tick_hz
            rows = [probe.as_vector()]
            for _ in range(PCA_WINDOW):
                probe = step(probe, dt)
                rows.append(probe.as_vector())

        matrix = np.asarray(rows, dtype=np.float64)
        matrix -= matrix.mean(axis=0, keepdims=True)
        if np.linalg.norm(matrix) < 1e-9:
            val = 0.0
        else:
            sv = np.linalg.svd(matrix, compute_uv=False)
            total = float(np.sum(sv**2)) or 1.0
            val = float(np.sum(sv[:3] ** 2)) / total

        self._pca_cache = (self.tick, val)
        return val

    async def advance(self) -> dict[str, Any] | None:
        prev_r = self.state.order_parameter()
        self.state = step(self.state, dt=1.0 / settings.tick_hz)
        self._state_window.append(self.state.as_vector())
        self.tick += 1
        curr_r = self.state.order_parameter()
        lyap = lyapunov_proxy(self.state)
        event = detect_event(self._prev_order, curr_r, lyap)
        self._prev_order = curr_r

        if event:
            telem = {**self.telemetry(), "event": event}
            witness = await generate_witness(telem)
            record = WitnessRecord(
                event=event,
                text=witness["text"],
                source=witness["source"],
                model=witness.get("model"),
                timestamp=time.time(),
                telemetry=telem,
            )
            self.witnesses.appendleft(record)
            self._log_activity("witness", record)
            await self._notify_monitor(record)
            return telem
        return None

    def steer(self, text: str) -> dict[str, Any]:
        kappa, bias = steer_from_text(text)
        self.state.kappa = kappa
        self.state.steering_bias = bias
        self._log_activity("steer", {"prompt": text, "kappa": kappa})
        return {"kappa": kappa, "applied": True, "prompt": text}

    def set_projection(self, theta1: float, theta2: float) -> dict[str, float]:
        self.projection_theta1 = theta1
        self.projection_theta2 = theta2
        px, py = stiefel_projection(self.state, theta1, theta2)
        return {"theta1": theta1, "theta2": theta2, "x": px, "y": py}

    def dream(self, steps: int = 60) -> dict[str, Any]:
        surr, truth, fit_info = dream_trajectory(self.state, steps=steps)
        divergence_idx = 0
        for i, (s, t) in enumerate(zip(surr, truth)):
            if np.hypot(s[0] - t[0], s[1] - t[1]) > 0.15:
                divergence_idx = i
                break
        result = {
            "surrogate": [{"x": a, "y": b} for a, b in surr],
            "truth": [{"x": a, "y": b} for a, b in truth],
            "divergence_at": divergence_idx,
            "steps": steps,
            "fit": fit_info,
        }
        self._log_activity("dream", {"steps": steps, "divergence_at": divergence_idx})
        return result

    def log_agent_invoke(
        self,
        capability_id: str,
        input_data: dict[str, Any],
        result: dict[str, Any],
        source: str = "aimarket",
    ) -> dict[str, Any]:
        output = result.get("output", result)
        record = {
            "capability_id": capability_id,
            "source": source,
            "input": input_data,
            "summary": self._summarize_invoke(capability_id, output),
            "is_prediction": capability_id in ("platon.dream@v1", "platon.oracle@v1"),
            "prediction": self._prediction_payload(capability_id, output),
            "timestamp": time.time(),
        }
        self._log_activity("agent_invoke", record)
        return record

    def _summarize_invoke(self, capability_id: str, output: dict[str, Any]) -> str:
        if capability_id == "platon.steer@v1":
            return f"κ→{output.get('kappa', '?'):.3f}" if isinstance(output.get("kappa"), (int, float)) else "steer"
        if capability_id == "platon.dream@v1":
            return f"prediction diverges @ step {output.get('divergence_at', '?')}"
        if capability_id == "platon.oracle@v1":
            text = output.get("text") or ""
            return text[:140] + ("…" if len(text) > 140 else "")
        if capability_id == "platon.state@v1":
            return f"r={output.get('order_parameter', '?')}, κ={output.get('kappa', '?')}"
        if capability_id == "platon.project@v1":
            return f"θ₁={output.get('theta1', '?')}, θ₂={output.get('theta2', '?')}"
        if capability_id == "platon.witnesses@v1":
            n = len(output.get("witnesses") or [])
            return f"{n} oracle testimonies"
        return capability_id

    def _prediction_payload(
        self, capability_id: str, output: dict[str, Any]
    ) -> dict[str, Any] | None:
        if capability_id == "platon.dream@v1":
            return {
                "surrogate": output.get("surrogate"),
                "truth": output.get("truth"),
                "divergence_at": output.get("divergence_at"),
            }
        if capability_id == "platon.oracle@v1":
            return {"text": output.get("text"), "event": output.get("event")}
        return None

    def _log_activity(self, kind: str, payload: Any) -> None:
        self.activity.appendleft(
            {
                "kind": kind,
                "timestamp": time.time(),
                "payload": payload if isinstance(payload, dict) else vars(payload),
            }
        )

    async def _notify_monitor(self, record: WitnessRecord) -> None:
        if not settings.alien_monitor_webhook:
            return
        try:
            import httpx

            async with httpx.AsyncClient(timeout=5.0) as client:
                await client.post(
                    settings.alien_monitor_webhook,
                    json={
                        "name": "Platon",
                        "type": "shadow-oracle",
                        "category": "math-viz",
                        "event": record.event,
                        "witness": record.text[:280],
                    },
                )
        except Exception:
            pass

    async def run_loop(self) -> None:
        self._running = True
        interval = 1.0 / settings.tick_hz
        while self._running:
            await self.advance()
            await asyncio.sleep(interval)

    def stop(self) -> None:
        self._running = False


engine = SimulationEngine()
