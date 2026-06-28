from __future__ import annotations

from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PLATON_", extra="ignore")

    host: str = "0.0.0.0"
    port: int = 9200
    public_url: str = "http://localhost:9200"

    # CORS: comma-separated origins. "*" disables credentials (a "*" + credentials
    # combination is invalid per the CORS spec and rejected by browsers).
    cors_origins: str = "*"

    # AIMarket hub (real federated hub the provider registers with).
    hub_url: str = "https://modelmarket.dev"
    hub_name: str = "Platon Shadow Oracle"
    hub_admin_token: Optional[str] = None

    # Oracle / witness LLM.
    oracle_enabled: bool = True
    oracle_fallback: bool = True
    oracle_provider: str = "auto"  # auto | deepseek | openai | anthropic | ollama | template
    oracle_max_tokens: int = 220
    oracle_temperature: float = 0.75
    # DeepSeek (OpenAI-compatible) — key via DEEPSEEK_API_KEY or PLATON_DEEPSEEK_API_KEY
    deepseek_api_key: Optional[str] = None
    deepseek_model: str = "deepseek-chat"
    deepseek_base_url: str = "https://api.deepseek.com/v1"
    # OpenAI — key via OPENAI_API_KEY or PLATON_OPENAI_API_KEY
    openai_api_key: Optional[str] = None
    openai_model: str = "gpt-4o-mini"
    openai_base_url: str = "https://api.openai.com/v1"
    # Anthropic — key via ANTHROPIC_API_KEY or PLATON_ANTHROPIC_API_KEY
    anthropic_api_key: Optional[str] = None
    anthropic_model: str = "claude-3-5-haiku-latest"
    anthropic_base_url: str = "https://api.anthropic.com/v1"
    # Local Ollama
    ollama_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "mistral:7b-instruct-q4_K_M"
    ollama_timeout_s: float = 30.0

    # Dynamics.
    n_oscillators: int = 32
    tick_hz: float = 30.0

    alien_monitor_webhook: Optional[str] = None
    signing_key_path: str = "data/platon_signing_key"

    # Post-quantum: when enabled (and dilithium-py is installed), signatures become
    # hybrid Ed25519 + ML-DSA-65 (FIPS 204). Additive — the Ed25519 part is
    # unchanged so the hub keeps verifying. Off by default.
    pqc_enabled: bool = False

    # Optional external transparency log / chain to anchor beacon checkpoints.
    beacon_anchor_webhook: Optional[str] = None


settings = Settings()
