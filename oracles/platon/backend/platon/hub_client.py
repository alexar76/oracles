"""Client for federating Platon with a real AIMarket hub (default: modelmarket.dev).

Self-registration via ``/federation/announce`` is admin-gated on the live hub
(503 unless the operator sets ``AIMARKET_ADMIN_TOKEN``); the intended path is
hub-pull: the operator adds our ``well_known_url`` to their seed list and the
crawler pulls + pins our signed manifest. These helpers therefore:

* self-verify our manifest with the exact 4-field hub canonical,
* fetch the hub's ``/.well-known`` to confirm reachability,
* attempt the announce (reporting the admin-gate cleanly),
* open a demo payment channel and run an intent search (both work live).
"""

from __future__ import annotations

from typing import Any, Optional

import httpx

from platon.aimarket import CAPABILITIES, manifest
from platon.config import settings
from platon.signing import Signer

_signer = Signer(settings.signing_key_path)


def announce_canonical(hub_url: str, well_known_url: str, capabilities_count: int) -> str:
    return (
        f"hub_url:{hub_url}"
        f"|well_known_url:{well_known_url}"
        f"|capabilities_count:{capabilities_count}"
    )


def self_verify_manifest() -> dict[str, Any]:
    """Recompute the hub's 4-field canonical and verify our own signature."""
    man = manifest()
    return {
        "ok": _signer.verify_manifest_signature(man),
        "capabilities": [t["capability_id"] for t in man["tools"]],
        "canonical": _signer.manifest_canonical(man),
        "signer_public_key": _signer.public_key_b64,
    }


def announce_body() -> dict[str, Any]:
    well_known_url = f"{settings.public_url.rstrip('/')}/.well-known/ai-market.json"
    count = len(CAPABILITIES)
    canonical = announce_canonical(settings.public_url, well_known_url, count)
    return {
        "hub_url": settings.public_url,
        "well_known_url": well_known_url,
        "capabilities_count": count,
        "hub_name": settings.hub_name,
        "signer_public_key": _signer.public_key_b64,
        "signature": {"algorithm": "ed25519", "value": _signer.sign_canonical(canonical)},
    }


async def hub_info(hub_url: Optional[str] = None) -> dict[str, Any]:
    base = (hub_url or settings.hub_url).rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(f"{base}/.well-known/ai-market.json")
            if resp.status_code == 200:
                d = resp.json()
                return {
                    "reachable": True,
                    "name": d.get("name"),
                    "hub_version": d.get("hub_version"),
                    "protocol_versions": d.get("protocol_versions"),
                    "payment_configured": d.get("payment_configured"),
                    "signer_public_key": d.get("signer_public_key"),
                }
            return {"reachable": False, "status": resp.status_code}
    except httpx.HTTPError as exc:
        return {"reachable": False, "error": str(exc)}


async def announce(
    hub_url: Optional[str] = None, admin_token: Optional[str] = None
) -> dict[str, Any]:
    base = (hub_url or settings.hub_url).rstrip("/")
    token = admin_token or settings.hub_admin_token or ""
    url = f"{base}/ai-market/v2/federation/announce"
    params = {"authorization": token} if token else {}
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(url, params=params, json=announce_body())
            body: Any
            try:
                body = resp.json()
            except ValueError:
                body = resp.text
            if resp.status_code == 200:
                return {"registered": True, "status": 200, "response": body}
            if resp.status_code == 503:
                return {
                    "registered": False,
                    "status": 503,
                    "reason": "admin-gated on the live hub (operator must seed/announce us)",
                    "response": body,
                }
            return {"registered": False, "status": resp.status_code, "response": body}
    except httpx.HTTPError as exc:
        return {"registered": False, "error": str(exc)}


async def open_channel(
    deposit_usd: float = 1.0,
    hub_url: Optional[str] = None,
    token: str = "USDT",
    chain: str = "base",
) -> dict[str, Any]:
    base = (hub_url or settings.hub_url).rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(
                f"{base}/ai-market/v2/channel/open",
                json={"deposit_usd": deposit_usd, "token": token, "chain": chain},
            )
            try:
                return {"status": resp.status_code, "response": resp.json()}
            except ValueError:
                return {"status": resp.status_code, "response": resp.text}
    except httpx.HTTPError as exc:
        return {"error": str(exc)}


async def invoke_capability(
    product_id: str,
    capability_id: str,
    payload: dict[str, Any],
    channel_id: Optional[str] = None,
    hub_url: Optional[str] = None,
    source_hub: str = "local",
) -> dict[str, Any]:
    """Consume a capability THROUGH the hub — Platon as a market consumer, not
    just a provider. Real protocol call; against the public demo the hub may
    return 402 (open a channel) or 503 (no execution backend) — reported as-is,
    never mocked."""
    base = (hub_url or settings.hub_url).rstrip("/")
    headers = {"X-AIMarket-Route-Ok": "true"}
    if channel_id:
        headers["X-Payment-Channel"] = channel_id
    body = {
        "product_id": product_id,
        "capability_id": capability_id,
        "source_hub": source_hub,
        "input": payload,
    }
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{base}/ai-market/v2/invoke", headers=headers, json=body
            )
            try:
                return {"status": resp.status_code, "response": resp.json()}
            except ValueError:
                return {"status": resp.status_code, "response": resp.text}
    except httpx.HTTPError as exc:
        return {"error": str(exc)}


async def search(
    intent: str,
    budget: float = 0.05,
    limit: int = 10,
    hub_url: Optional[str] = None,
) -> dict[str, Any]:
    base = (hub_url or settings.hub_url).rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(
                f"{base}/ai-market/v2/search",
                params={"intent": intent, "budget": budget, "limit": limit},
            )
            try:
                return {"status": resp.status_code, "response": resp.json()}
            except ValueError:
                return {"status": resp.status_code, "response": resp.text}
    except httpx.HTTPError as exc:
        return {"error": str(exc)}
