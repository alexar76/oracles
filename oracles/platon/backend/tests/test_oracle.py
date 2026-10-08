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


# --- 2026-09 re-audit: platon.verify@v1 must answer the question it advertises -------
#
# The capability is described as "Verify a Platon chaos-VRF draw". The handler passed
# `d.get("public_key")` into verify_randomness, and verify_randomness falls back to
# `sig.get("public_key")` — the key embedded in the caller's OWN document. So both the
# pinned key and the fallback were caller-controlled, and the capability actually answered
# "is this document internally consistent under whatever key it carries", which is a
# question anybody can make come out True by signing their own draw with their own key.
# The answer then ships inside a Platon-SIGNED receipt, so a downstream consumer reads it
# as Platon vouching for the draw.

def test_a_draw_signed_by_a_stranger_is_not_valid():
    import platon.aimarket as A
    from platon.randomness import randomness_canonical
    from platon.signing import Signer

    stranger = Signer("/tmp/platon-stranger-verify.key")
    # Take a genuine draw for its exact proof shape, then re-sign the whole thing with a
    # key that is not the oracle's. Everything an attacker controls, and nothing they don't.
    genuine = A._HANDLERS["platon.random@v1"]({"num_bytes": 32})
    random_hex, proof = genuine["random_hex"], genuine["proof"]
    canonical = randomness_canonical(random_hex, proof)
    forged = {
        "random_hex": random_hex,
        "proof": proof,
        "signature": {"public_key": stranger.public_key_b64,
                      "value": stranger.sign_canonical(canonical)},
    }

    out = A._HANDLERS["platon.verify@v1"](dict(forged))
    assert out["valid"] is False, (
        "the oracle vouched for a draw signed by a key that is not its own"
    )

    # And naming the stranger's key explicitly must not help either.
    out2 = A._HANDLERS["platon.verify@v1"]({**forged, "public_key": stranger.public_key_b64})
    assert out2["valid"] is False


def test_a_genuine_platon_draw_still_verifies():
    """The capability has to keep working for the thing it is for."""
    import platon.aimarket as A

    drawn = A._HANDLERS["platon.random@v1"]({"num_bytes": 32})
    out = A._HANDLERS["platon.verify@v1"]({
        "random_hex": drawn["random_hex"],
        "proof": drawn["proof"],
        "signature": drawn["signature"],
    })
    assert out["valid"] is True, drawn
