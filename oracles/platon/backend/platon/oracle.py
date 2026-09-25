"""Witness oracle — multi-provider LLM or deterministic fallback."""

from __future__ import annotations

import os
import threading
import time
from collections import deque
from typing import Any

from platon.config import settings
from platon.oracle_providers import generate_text, list_provider_status


WITNESS_TEMPLATES = {
    "chimera_birth": (
        "κ={kappa:.3f} · r={order_parameter:.3f} — order did not win; it negotiated. "
        "Some oscillators sing in unison, others pretend to be noise. "
        "You watch the shadow of a {dim}D compromise."
    ),
    "chimera_death": (
        "Chimera dissolved at κ={kappa:.3f}. Coherence boundary erased — "
        "uniform chaos again, Lyapunov={lyapunov:.4f}."
    ),
    "chaos_threshold": (
        "Predictability died: λ≈{lyapunov:.4f}. Neural nets go blind here — "
        "only the projection remains, not the source."
    ),
    "full_synchronization": (
        "Full synchronization r={order_parameter:.3f}. All {dim} dimensions whisper one phase. "
        "Plato's cave fully lit — yet you still see only 2D."
    ),
}

_ORACLE_SYSTEM = (
    "You are a mathematical oracle for Platon UMBRAL — a 32D coupled Stuart-Landau / "
    "Kuramoto dynamical system. Write one short witness (2–3 sentences): poetic, precise, "
    "no clichés. Reference κ, r, λ when relevant."
)


class _Defaulting(dict):
    """format_map source that renders a missing/unformattable field instead of raising.

    A witness template is a presentation detail; a KeyError here used to turn into a 500
    on a public route.
    """

    def __missing__(self, key: str) -> str:
        return "n/a"


#: LLM witnesses allowed per minute, across every caller and the tick loop together.
#: Two paths spend the operator's provider key here and neither was bounded: the
#: simulation calls generate_witness on every detected event, so ONE anonymous steer that
#: pins the system in a permanently event-firing state drives back-to-back completions;
#: and platon.oracle@v1 relays caller-supplied telemetry into a completion per request.
#: Over budget we fall through to WITNESS_TEMPLATES -- a real answer, just not a paid one.
_WITNESS_LLM_PER_MIN = max(1, int(os.environ.get("PLATON_WITNESS_LLM_PER_MIN", "20") or 20))
_WITNESS_WINDOW_S = 60.0
_witness_calls: deque[float] = deque()
_witness_lock = threading.Lock()


def _witness_llm_budget_available() -> bool:
    now = time.monotonic()
    with _witness_lock:
        while _witness_calls and _witness_calls[0] <= now - _WITNESS_WINDOW_S:
            _witness_calls.popleft()
        if len(_witness_calls) >= _WITNESS_LLM_PER_MIN:
            return False
        _witness_calls.append(now)
        return True


async def generate_witness(telemetry: dict) -> dict:
    event = telemetry.get("event", "observation")
    if (
        settings.oracle_enabled
        and settings.oracle_provider.lower() != "template"
        and _witness_llm_budget_available()
    ):
        user = f"Event telemetry (JSON): {telemetry}\nWrite the oracle witness."
        llm_text, meta = await generate_text(_ORACLE_SYSTEM, user)
        if llm_text:
            return {
                "event": event,
                "text": llm_text,
                "source": meta.get("source", "llm"),
                "model": meta.get("model"),
            }

    if not settings.oracle_fallback:
        return {
            "event": event,
            "text": "oracle unavailable: no LLM reachable and template fallback disabled",
            "source": "unavailable",
            "model": None,
        }

    template = WITNESS_TEMPLATES.get(
        event,
        (
            "Observation: κ={kappa:.3f}, r={order_parameter:.3f}, λ={lyapunov:.4f}. "
            "One reality — many incompatible projections."
        ),
    )
    # Telemetry can carry caller-supplied keys (platon.oracle@v1 accepts a telemetry
    # object), so it must not be splatted into format() where a colliding "dim" raises
    # TypeError -> unauthenticated 500, and a missing key raises KeyError. Build the
    # namespace explicitly and answer with the raw numbers if the template cannot render.
    fields: dict[str, Any] = {"dim": settings.n_oscillators}
    fields.update(telemetry)
    fields["dim"] = settings.n_oscillators
    try:
        text = template.format_map(_Defaulting(fields))
    except (ValueError, IndexError):
        text = (
            f"Observation: event={event} "
            f"kappa={fields.get('kappa')} r={fields.get('order_parameter')} "
            f"lambda={fields.get('lyapunov')}."
        )
    return {"event": event, "text": text, "source": "template", "model": None}


def oracle_info() -> dict:
    providers = list_provider_status()
    configured = [p for p in providers if p.configured]
    return {
        "enabled": settings.oracle_enabled,
        "provider_mode": settings.oracle_provider,
        "fallback_to_template": settings.oracle_fallback,
        "active_chain": [p.name for p in configured],
        "providers": [
            {
                "name": p.name,
                "type": p.provider_type,
                "model": p.model,
                "configured": p.configured,
                "base_url": p.base_url,
            }
            for p in providers
        ],
    }
