"""Witness oracle — multi-provider LLM or deterministic fallback."""

from __future__ import annotations

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


async def generate_witness(telemetry: dict) -> dict:
    event = telemetry.get("event", "observation")
    if settings.oracle_enabled and settings.oracle_provider.lower() != "template":
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
    text = template.format(dim=settings.n_oscillators, **telemetry)
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
