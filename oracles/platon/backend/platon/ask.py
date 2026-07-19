"""platon.ask — a grounded, read-only informational guide.

A curious user (or agent) asks a question; we answer it using (a) a distilled
knowledge base about Platon and (b) the LIVE state of the running system
(telemetry, the latest witness, the beacon, the capability catalog). The LLM
path reuses the same DeepSeek/Ollama providers as the oracle, with an honest
deterministic fallback when no model is configured.

Read-only by construction: this module never mutates the engine. The system
prompt also forbids the model from claiming to perform actions — and since it is
given no tools, prompt-injection cannot cause side effects (see docs/SECURITY.md).
"""

from __future__ import annotations

import os

import httpx

from platon.config import settings

_LANG_NAME = {"en": "English", "ru": "Russian", "es": "Spanish"}

MAX_QUESTION = 500

KNOWLEDGE = (
    "Platon UMBRAL is an INDEPENDENT project (not produced by AI-Factory) that plugs "
    "into the alexar76 AI agent economy via AIMarket Protocol v2. It is a verifiable "
    "randomness beacon and dynamical oracle built on 32 coupled Stuart-Landau / Kuramoto "
    "oscillators (state in R^64). Core math (real, provable): RK2 integration; Kuramoto "
    "order parameter r=|mean(e^{i*theta})| in [0,1] (1=full sync); a finite-time Lyapunov "
    "proxy lambda (chaos when high); an orthonormal Stiefel-frame 2D projection of the 64D "
    "state; pca_energy_3 = fraction of recent-trajectory variance in the top 3 modes "
    "(1=low-dim/synchronized, lower=high-dim/chaotic). kappa is the coupling strength. "
    "Capabilities: platon.random@v1 (Ed25519-signed random bytes + proof), platon.beacon@v1 "
    "(hash-chained tamper-evident rounds), platon.oracle@v1 (LLM witness at bifurcations), "
    "platon.state/steer/project/dream/witnesses. Every invoke returns a signed receipt and a "
    "sha256 input_hash; manifest is Ed25519-signed and verifies against the hub canonical. "
    "Where the AI is: the oracle + this guide are LLMs; DREAM trains a real least-squares "
    "linear model on trajectory data (measurable residual, no magic constants); the consumers "
    "are autonomous AI agents. Security: the SHA-256 hash chain is quantum-safe (Grover -> "
    "2^128); Ed25519 signatures are the one quantum-exposed part (Shor on a future quantum "
    "computer) -> hybrid + post-quantum (ML-DSA/SLH-DSA) migration is planned; randomness is a "
    "trusted signed beacon today (commit-reveal/ECVRF would make it trustless). Steering maps "
    "text -> kappa and per-oscillator frequency bias via SHA-256 (deterministic, not semantic "
    "understanding). The hub (modelmarket.dev) handles discovery, payment channels and receipts."
)


def build_live_context(engine) -> str:
    t = engine.telemetry()
    parts = [
        f"tick={t['tick']}",
        f"kappa={t['kappa']}",
        f"order_parameter r={t['order_parameter']}",
        f"lyapunov lambda={t['lyapunov']}",
        f"pca_energy_3={t['pca_energy_3']}",
    ]
    if engine.witnesses:
        w = engine.witnesses[0]
        parts.append(f"latest_event={w.event} (\"{w.text[:160]}\")")
    try:
        from platon.aimarket import CAPABILITIES, beacon

        latest = beacon.latest()
        if latest:
            parts.append(f"beacon_round={latest['round']} chain_len={len(beacon.rounds)}")
        parts.append(
            "capabilities=" + ", ".join(c["capability_id"] for c in CAPABILITIES)
        )
    except Exception:
        pass
    return "; ".join(parts)


def _system_prompt(lang: str, context: str) -> str:
    lang_name = _LANG_NAME.get(lang, "English")
    return (
        f"You are Platon's informational guide for curious visitors. Answer ONLY about "
        f"Platon and what is on screen, concisely (3-6 sentences), in {lang_name}. "
        f"You are READ-ONLY: never claim to change kappa, steer, or invoke anything; if "
        f"asked to act, explain how the user/agent would do it instead. Prefer the LIVE "
        f"STATE numbers when relevant. If you don't know, say so. Do not invent prices or "
        f"guarantees.\n\nKNOWLEDGE:\n{KNOWLEDGE}\n\nLIVE STATE: {context}"
    )


def _deepseek_key() -> str | None:
    return settings.deepseek_api_key or os.environ.get("DEEPSEEK_API_KEY") or None


async def _deepseek_chat(system: str, user: str) -> str | None:
    key = _deepseek_key()
    if not key:
        return None
    base = settings.deepseek_base_url.rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{base}/chat/completions",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={
                    "model": settings.deepseek_model,
                    "max_tokens": 300,
                    "temperature": 0.3,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                },
            )
            if resp.status_code == 200:
                choice = (resp.json().get("choices") or [{}])[0]
                return ((choice.get("message") or {}).get("content") or "").strip() or None
    except httpx.HTTPError:
        pass
    return None


async def _ollama_chat(system: str, user: str) -> str | None:
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{settings.ollama_url}/api/generate",
                json={
                    "model": settings.ollama_model,
                    "system": system,
                    "prompt": user,
                    "stream": False,
                    "options": {"temperature": 0.3, "num_predict": 320},
                },
            )
            if resp.status_code == 200:
                return (resp.json().get("response") or "").strip() or None
    except httpx.HTTPError:
        pass
    return None


def _fallback(question: str, lang: str, context: str) -> str:
    intro = {
        "ru": "LLM не настроен — вот живое состояние системы:",
        "es": "LLM no configurado — aquí está el estado en vivo:",
        "en": "LLM not configured — here is the live system state:",
    }.get(lang, "LLM not configured — here is the live system state:")
    tail = {
        "ru": "Подробности — в docs/ECOSYSTEM.md и docs/SECURITY.md.",
        "es": "Más detalles en docs/ECOSYSTEM.md y docs/SECURITY.md.",
        "en": "See docs/ECOSYSTEM.md and docs/SECURITY.md for details.",
    }.get(lang, "See docs/ECOSYSTEM.md and docs/SECURITY.md for details.")
    return f"{intro} {context}. {tail}"


async def answer(question: str, lang: str, engine) -> dict:
    question = (question or "").strip()[:MAX_QUESTION]
    if not question:
        return {"answer": "", "source": "empty", "lang": lang}

    context = build_live_context(engine)
    if settings.oracle_enabled:
        system = _system_prompt(lang, context)
        text = await _deepseek_chat(system, question)
        if text:
            return {"answer": text, "source": "deepseek", "lang": lang}
        text = await _ollama_chat(system, question)
        if text:
            return {"answer": text, "source": "ollama", "lang": lang}

    return {"answer": _fallback(question, lang, context), "source": "fallback", "lang": lang}
