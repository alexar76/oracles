"""Oracle LLM providers — OpenAI-compatible, Anthropic, Ollama."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Literal

import httpx

from platon.config import settings

ProviderName = Literal["deepseek", "openai", "anthropic", "ollama"]

AUTO_CHAIN: tuple[ProviderName, ...] = ("deepseek", "openai", "anthropic", "ollama")


@dataclass(frozen=True)
class ProviderStatus:
    name: str
    provider_type: str
    model: str
    configured: bool
    base_url: str


def _env(key: str) -> str | None:
    val = os.environ.get(key, "").strip()
    return val or None


def _provider_configs() -> dict[ProviderName, dict[str, Any]]:
    return {
        "deepseek": {
            "provider_type": "openai_compatible",
            "api_key": settings.deepseek_api_key or _env("DEEPSEEK_API_KEY"),
            "base_url": settings.deepseek_base_url,
            "model": settings.deepseek_model,
        },
        "openai": {
            "provider_type": "openai_compatible",
            "api_key": settings.openai_api_key or _env("OPENAI_API_KEY"),
            "base_url": settings.openai_base_url,
            "model": settings.openai_model,
        },
        "anthropic": {
            "provider_type": "anthropic",
            "api_key": settings.anthropic_api_key or _env("ANTHROPIC_API_KEY"),
            "base_url": settings.anthropic_base_url,
            "model": settings.anthropic_model,
        },
        "ollama": {
            "provider_type": "ollama",
            "api_key": None,
            "base_url": settings.ollama_url,
            "model": settings.ollama_model,
        },
    }


def list_provider_status() -> list[ProviderStatus]:
    statuses: list[ProviderStatus] = []
    for name, conf in _provider_configs().items():
        ptype = conf["provider_type"]
        if ptype == "ollama":
            configured = True
        else:
            configured = bool(conf.get("api_key"))
        statuses.append(
            ProviderStatus(
                name=name,
                provider_type=ptype,
                model=str(conf["model"]),
                configured=configured,
                base_url=str(conf["base_url"]).rstrip("/"),
            )
        )
    return statuses


def resolve_provider_chain() -> list[ProviderName]:
    choice = settings.oracle_provider.lower().strip()
    if choice == "template":
        return []
    if choice == "auto":
        chain: list[ProviderName] = []
        for name in AUTO_CHAIN:
            conf = _provider_configs()[name]
            if conf["provider_type"] == "ollama":
                chain.append(name)
            elif conf.get("api_key"):
                chain.append(name)
        return chain
    if choice in _provider_configs():
        return [choice]  # type: ignore[list-item]
    return list(AUTO_CHAIN)


async def generate_text(system: str, user: str) -> tuple[str | None, dict[str, str | None]]:
    for name in resolve_provider_chain():
        conf = _provider_configs()[name]
        ptype = conf["provider_type"]
        if ptype == "openai_compatible":
            if not conf["api_key"]:
                continue
            text = await _openai_compatible(
                base_url=conf["base_url"],
                api_key=conf["api_key"],
                model=conf["model"],
                system=system,
                user=user,
            )
            if text:
                return text, {"source": name, "model": conf["model"]}
        elif ptype == "anthropic":
            if not conf["api_key"]:
                continue
            text = await _anthropic(
                base_url=conf["base_url"],
                api_key=conf["api_key"],
                model=conf["model"],
                system=system,
                user=user,
            )
            if text:
                return text, {"source": name, "model": conf["model"]}
        elif ptype == "ollama":
            text = await _ollama(
                base_url=conf["base_url"],
                model=conf["model"],
                system=system,
                user=user,
            )
            if text:
                return text, {"source": "ollama", "model": conf["model"]}
    return None, {}


async def _openai_compatible(
    *,
    base_url: str,
    api_key: str,
    model: str,
    system: str,
    user: str,
) -> str | None:
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{base_url.rstrip('/')}/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "max_tokens": settings.oracle_max_tokens,
                    "temperature": settings.oracle_temperature,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                },
            )
            if resp.status_code == 200:
                data = resp.json()
                choice = (data.get("choices") or [{}])[0]
                text = (choice.get("message") or {}).get("content", "")
                return text.strip() or None
    except httpx.HTTPError:
        pass
    return None


async def _anthropic(
    *,
    base_url: str,
    api_key: str,
    model: str,
    system: str,
    user: str,
) -> str | None:
    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
            resp = await client.post(
                f"{base_url.rstrip('/')}/messages",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "max_tokens": settings.oracle_max_tokens,
                    "system": system,
                    "messages": [{"role": "user", "content": user}],
                },
            )
            if resp.status_code == 200:
                data = resp.json()
                blocks = data.get("content") or []
                text = "".join(
                    b.get("text", "") for b in blocks if b.get("type") == "text"
                )
                return text.strip() or None
    except httpx.HTTPError:
        pass
    return None


async def _ollama(
    *,
    base_url: str,
    model: str,
    system: str,
    user: str,
) -> str | None:
    prompt = f"{system}\n\n{user}"
    try:
        async with httpx.AsyncClient(timeout=settings.ollama_timeout_s) as client:
            resp = await client.post(
                f"{base_url.rstrip('/')}/api/generate",
                json={
                    "model": model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": settings.oracle_temperature,
                        "num_predict": settings.oracle_max_tokens,
                    },
                },
            )
            if resp.status_code == 200:
                return resp.json().get("response", "").strip() or None
    except httpx.HTTPError:
        pass
    return None
