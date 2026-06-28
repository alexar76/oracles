"""Tests for multi-provider oracle."""

from unittest.mock import AsyncMock, patch

import pytest

from platon.oracle import generate_witness, oracle_info
from platon.oracle_providers import generate_text, resolve_provider_chain


@pytest.mark.asyncio
async def test_generate_witness_template_fallback(monkeypatch):
    monkeypatch.setenv("PLATON_ORACLE_PROVIDER", "template")
    from platon.config import settings

    settings.oracle_provider = "template"
    result = await generate_witness(
        {"event": "chaos_threshold", "kappa": 0.5, "order_parameter": 0.4, "lyapunov": 3.0}
    )
    assert result["source"] == "template"
    assert "λ" in result["text"] or "Lyapunov" in result["text"] or "Predictability" in result["text"]


@pytest.mark.asyncio
async def test_openai_provider_used(monkeypatch):
    monkeypatch.setenv("PLATON_ORACLE_PROVIDER", "openai")
    from platon.config import settings

    settings.oracle_provider = "openai"
    settings.openai_api_key = "sk-test"

    with patch(
        "platon.oracle_providers._openai_compatible",
        new_callable=AsyncMock,
        return_value="Witness from OpenAI.",
    ) as mock_openai:
        text, meta = await generate_text("sys", "user")
    assert text == "Witness from OpenAI."
    assert meta["source"] == "openai"
    mock_openai.assert_called_once()


@pytest.mark.asyncio
async def test_anthropic_provider_used(monkeypatch):
    monkeypatch.setenv("PLATON_ORACLE_PROVIDER", "anthropic")
    from platon.config import settings

    settings.oracle_provider = "anthropic"
    settings.anthropic_api_key = "ant-test"

    with patch(
        "platon.oracle_providers._anthropic",
        new_callable=AsyncMock,
        return_value="Witness from Claude.",
    ):
        text, meta = await generate_text("sys", "user")
    assert meta["source"] == "anthropic"


def test_auto_chain_skips_missing_keys(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    from platon.config import settings

    settings.oracle_provider = "auto"
    settings.deepseek_api_key = None
    settings.openai_api_key = None
    settings.anthropic_api_key = None
    chain = resolve_provider_chain()
    assert chain == ["ollama"]


def test_oracle_info_lists_providers():
    info = oracle_info()
    assert "providers" in info
    names = {p["name"] for p in info["providers"]}
    assert names == {"deepseek", "openai", "anthropic", "ollama"}
