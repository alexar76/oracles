"""AIMarket Protocol v2 integration — discovery, manifest, invoke."""

from __future__ import annotations

import hashlib
import json
import secrets
import time
from datetime import datetime, timezone
from typing import Any

from platon.commit_reveal import CommitRevealBeacon
from platon.config import settings
from platon.metrics import metrics
from platon.randomness import Beacon, draw_randomness, verify_randomness
from platon.signing import Signer
from platon.simulation import engine

_signer = Signer(settings.signing_key_path)
beacon = Beacon(_signer)
cr_beacon = CommitRevealBeacon(_signer)


def utc_now_z() -> str:
    """Second-precision ISO-8601 UTC with a trailing Z — the form the AIMarket
    hub and JSON-schema ``date-time`` validators expect (not microseconds+offset)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def input_hash(input_data: dict[str, Any]) -> str:
    """SHA-256 of the canonical (sorted-key) JSON of the input — a real hash."""
    canonical = json.dumps(input_data, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode()).hexdigest()


def well_known() -> dict[str, Any]:
    base = settings.public_url.rstrip("/")
    return {
        "name": settings.hub_name,
        "protocol_versions": ["v2"],
        "hub_version": "0.1.0",
        "manifest_url": f"{base}/ai-market/v2/manifest",
        "mcp_endpoint": f"{base}/ai-market/v2/invoke",
        "capabilities_count": len(CAPABILITIES),
        "signer_public_key": _signer.public_key_b64,
        "description": (
            "Platon UMBRAL — 32D dynamical shadow oracle. "
            "Verifiable randomness beacon, dynamical oracle, chaos steering."
        ),
        "categories": [
            "randomness-beacon",
            "oracle",
            "simulation",
            "math-viz",
            "agent-tooling",
        ],
        # Legacy aliases kept for direct consumers and docs.
        "protocol_version": "v2",
        "hub_name": settings.hub_name,
        "hub_url": base,
        "capabilities_endpoint": f"{base}/ai-market/v2/manifest",
        "invoke_endpoint": f"{base}/ai-market/v2/invoke",
        "ecosystem": {
            "project": "platon",
            "author": "alexar76",
            "related": [
                "https://github.com/alexar76/alien-monitor",
                "https://github.com/alexar76/aimarket-hub",
                "https://magic-ai-factory.com/monitor/",
            ],
        },
    }


CAPABILITIES: list[dict[str, Any]] = [
    {
        "name": "platon.state",
        "capability_id": "platon.state@v1",
        "product_id": "prod-platon",
        "description": "Snapshot of the 32D universe — telemetry, oscillators, projection.",
        "input_schema": {"type": "object", "properties": {}},
        "output_schema": {"type": "object"},
        "price_per_call_usd": 0.001,
        "p50_latency_ms": 5,
        "success_rate_30d": 0.999,
    },
    {
        "name": "platon.random",
        "capability_id": "platon.random@v1",
        "product_id": "prod-platon",
        "description": (
            "Verifiable randomness drawn from the 32D chaotic shadow. Returns "
            "random bytes + reproducibility proof + Ed25519 signature, so consumers "
            "(mesh, hub, apps) can audit the draw. Optional client_seed (commit-reveal)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "num_bytes": {"type": "integer", "minimum": 1, "maximum": 64, "default": 32},
                "client_seed": {
                    "type": "string",
                    "description": "Optional client entropy mixed into the draw.",
                },
            },
        },
        "output_schema": {
            "type": "object",
            "required": ["random_hex", "proof", "signature"],
            "properties": {
                "random_hex": {"type": "string"},
                "num_bytes": {"type": "integer"},
                "proof": {
                    "type": "object",
                    "required": ["scheme", "state_hash", "client_seed", "tick", "timestamp"],
                    "properties": {
                        "scheme": {"type": "string"},
                        "state_hash": {"type": "string"},
                        "client_seed": {"type": "string"},
                        "tick": {"type": "integer"},
                        "timestamp": {"type": "string", "format": "date-time"},
                    },
                },
                "signature": {
                    "type": "object",
                    "required": ["algorithm", "public_key", "value"],
                    "properties": {
                        "algorithm": {"type": "string", "const": "ed25519"},
                        "public_key": {"type": "string"},
                        "value": {"type": "string"},
                    },
                },
            },
        },
        "price_per_call_usd": 0.004,
        "p50_latency_ms": 10,
        "success_rate_30d": 0.999,
    },
    {
        "name": "platon.verify",
        "capability_id": "platon.verify@v1",
        "product_id": "prod-platon",
        "description": (
            "Verify a Platon chaos-VRF draw: checks the Ed25519 signature over "
            "random_hex + reproducibility proof without re-running the engine."
        ),
        "input_schema": {
            "type": "object",
            "required": ["random_hex", "proof", "signature"],
            "properties": {
                "random_hex": {"type": "string"},
                "proof": {"type": "object"},
                "signature": {"type": "object"},
                "public_key": {"type": "string"},
            },
        },
        "output_schema": {
            "type": "object",
            "required": ["valid"],
            "properties": {"valid": {"type": "boolean"}},
        },
        "price_per_call_usd": 0.001,
        "p50_latency_ms": 5,
        "success_rate_30d": 0.999,
    },
    {
        "name": "platon.beacon",
        "capability_id": "platon.beacon@v1",
        "product_id": "prod-platon",
        "description": (
            "Hash-chained verifiable randomness beacon. Emits a signed round "
            "linked to the previous round_hash (drand-style, tamper-evident). "
            "Each round is independently verifiable and chains to its predecessor."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "num_bytes": {"type": "integer", "minimum": 1, "maximum": 64, "default": 32},
                "client_seed": {"type": "string"},
            },
        },
        "output_schema": {
            "type": "object",
            "required": ["round", "prev_hash", "random_hex", "round_hash", "signature"],
            "properties": {
                "round": {"type": "integer"},
                "prev_hash": {"type": "string"},
                "random_hex": {"type": "string"},
                "round_hash": {"type": "string"},
                "proof": {"type": "object"},
                "signature": {"type": "object"},
            },
        },
        "price_per_call_usd": 0.004,
        "p50_latency_ms": 10,
        "success_rate_30d": 0.999,
    },
    {
        "name": "platon.steer",
        "capability_id": "platon.steer@v1",
        "product_id": "prod-platon",
        "description": "Semantic steering — natural language maps to bifurcation parameters κ and ω bias.",
        "input_schema": {
            "type": "object",
            "required": ["prompt"],
            "properties": {"prompt": {"type": "string", "minLength": 1}},
        },
        "price_per_call_usd": 0.005,
        "p50_latency_ms": 12,
        "success_rate_30d": 0.998,
    },
    {
        "name": "platon.project",
        "capability_id": "platon.project@v1",
        "product_id": "prod-platon",
        "description": "Rotate the Stiefel projection — change how the 32D shadow appears in 2D.",
        "input_schema": {
            "type": "object",
            "required": ["theta1", "theta2"],
            "properties": {
                "theta1": {"type": "number"},
                "theta2": {"type": "number"},
            },
        },
        "price_per_call_usd": 0.002,
        "p50_latency_ms": 4,
        "success_rate_30d": 0.999,
    },
    {
        "name": "platon.dream",
        "capability_id": "platon.dream@v1",
        "product_id": "prod-platon",
        "description": "Surrogate vs truth trajectory — see where prediction dies at chaos.",
        "input_schema": {
            "type": "object",
            "properties": {"steps": {"type": "integer", "minimum": 10, "maximum": 120}},
        },
        "price_per_call_usd": 0.008,
        "p50_latency_ms": 25,
        "success_rate_30d": 0.997,
    },
    {
        "name": "platon.oracle",
        "capability_id": "platon.oracle@v1",
        "product_id": "prod-platon",
        "description": "Generate a mathematical witness for the latest dynamical event.",
        "input_schema": {
            "type": "object",
            "properties": {
                "event": {"type": "string"},
                "telemetry": {"type": "object"},
            },
        },
        "price_per_call_usd": 0.02,
        "p50_latency_ms": 800,
        "success_rate_30d": 0.95,
    },
    {
        "name": "platon.commit",
        "capability_id": "platon.commit@v1",
        "product_id": "prod-platon",
        "description": (
            "Commit-reveal randomness, phase 1. Returns a signed, timestamped "
            "commitment to a secret preimage BEFORE you send your seed — so the "
            "provider cannot grind/bias the result. Follow with platon.reveal@v1."
        ),
        "input_schema": {"type": "object", "properties": {}},
        "output_schema": {
            "type": "object",
            "required": ["round", "commitment", "signature"],
            "properties": {
                "round": {"type": "integer"},
                "commitment": {"type": "string"},
                "committed_at": {"type": "string"},
                "signature": {"type": "object"},
            },
        },
        "price_per_call_usd": 0.004,
        "p50_latency_ms": 8,
        "success_rate_30d": 0.999,
    },
    {
        "name": "platon.reveal",
        "capability_id": "platon.reveal@v1",
        "product_id": "prod-platon",
        "description": (
            "Commit-reveal randomness, phase 2. Supply the round + your client_seed; "
            "returns the revealed preimage + output = H(preimage‖client_seed) + proof. "
            "Verify: commitment binds the preimage, and the output derives from it."
        ),
        "input_schema": {
            "type": "object",
            "required": ["round"],
            "properties": {
                "round": {"type": "integer"},
                "client_seed": {"type": "string"},
                "num_bytes": {"type": "integer", "minimum": 1, "maximum": 64, "default": 32},
            },
        },
        "output_schema": {
            "type": "object",
            "required": ["round", "preimage", "client_seed", "random_hex", "signature"],
            "properties": {
                "round": {"type": "integer"},
                "commitment": {"type": "string"},
                "preimage": {"type": "string"},
                "client_seed": {"type": "string"},
                "random_hex": {"type": "string"},
                "commit_signature": {"type": "object"},
                "signature": {"type": "object"},
            },
        },
        "price_per_call_usd": 0.004,
        "p50_latency_ms": 8,
        "success_rate_30d": 0.998,
    },
    {
        "name": "platon.ask",
        "capability_id": "platon.ask@v1",
        "product_id": "prod-platon",
        "description": (
            "Grounded, read-only informational guide. Ask about the live system, the "
            "math, the capabilities, or the security model; answers use the current "
            "telemetry + a distilled knowledge base. Localized (en/ru/es)."
        ),
        "input_schema": {
            "type": "object",
            "required": ["question"],
            "properties": {
                "question": {"type": "string", "minLength": 1, "maxLength": 500},
                "lang": {"type": "string", "enum": ["en", "ru", "es"], "default": "en"},
            },
        },
        "output_schema": {
            "type": "object",
            "required": ["answer", "source", "lang"],
            "properties": {
                "answer": {"type": "string"},
                "source": {"type": "string"},
                "lang": {"type": "string"},
            },
        },
        "price_per_call_usd": 0.003,
        "p50_latency_ms": 700,
        "success_rate_30d": 0.97,
    },
    {
        "name": "platon.witnesses",
        "capability_id": "platon.witnesses@v1",
        "product_id": "prod-platon",
        "description": "Public feed of oracle testimonies — chimera births, chaos thresholds.",
        "input_schema": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 50}},
        },
        "price_per_call_usd": 0.001,
        "p50_latency_ms": 8,
        "success_rate_30d": 0.999,
    },
]


def _tool_with_metrics(cap: dict[str, Any]) -> dict[str, Any]:
    """Overlay measured latency / success onto the declared baseline."""
    tool = dict(cap)
    cid = cap["capability_id"]
    observed = metrics.count(cid)
    p50 = metrics.p50_latency_ms(cid)
    sr = metrics.success_rate(cid)
    if p50 is not None:
        tool["p50_latency_ms"] = round(p50, 2)
    if sr is not None:
        tool["success_rate_30d"] = round(sr, 4)
    tool["calls_observed"] = observed
    tool["metrics_source"] = "measured" if observed else "declared"
    return tool


def manifest() -> dict[str, Any]:
    tools = [_tool_with_metrics(c) for c in CAPABILITIES]
    body = {
        "protocol_version": "v2",
        "release_version": "0.1.0",
        "generated_at": utc_now_z(),
        "base_url": settings.public_url,
        "products_count": 1,
        "capabilities_count": len(tools),
        "total_capabilities": len(tools),
        "local_capabilities": len(tools),
        "federated_capabilities": 0,
        "hubs_indexed": 0,
        "tools": tools,
    }
    body["signature"] = _signer.sign_manifest(body)
    return body


def _capability(capability_id: str) -> dict[str, Any]:
    for cap in CAPABILITIES:
        if cap["capability_id"] == capability_id:
            return cap
    raise ValueError(f"Unknown capability: {capability_id}")


_HANDLERS = {
    "platon.state@v1": lambda _: engine.telemetry(),
    "platon.random@v1": lambda d: draw_randomness(
        engine.state.as_vector(),
        engine.tick,
        utc_now_z(),
        _signer,
        num_bytes=d.get("num_bytes", 32),
        client_seed=d.get("client_seed", ""),
    ),
    "platon.verify@v1": lambda d: {
        "valid": verify_randomness(
            {"random_hex": d["random_hex"], "proof": d["proof"], "signature": d["signature"]},
            d.get("public_key"),
        )
    },
    "platon.beacon@v1": lambda d: beacon.emit(
        engine.state.as_vector(),
        engine.tick,
        utc_now_z(),
        num_bytes=d.get("num_bytes", 32),
        client_seed=d.get("client_seed", ""),
    ),
    "platon.commit@v1": lambda d: cr_beacon.commit(
        engine.state.as_vector(), engine.tick, utc_now_z()
    ),
    "platon.reveal@v1": lambda d: cr_beacon.reveal(
        d["round"], d.get("client_seed", ""), utc_now_z(), num_bytes=d.get("num_bytes", 32)
    ),
    "platon.steer@v1": lambda d: engine.steer(d["prompt"]),
    "platon.project@v1": lambda d: engine.set_projection(d["theta1"], d["theta2"]),
    "platon.dream@v1": lambda d: engine.dream(d.get("steps", 60)),
    "platon.witnesses@v1": lambda d: {
        "witnesses": [
            {
                "event": w.event,
                "text": w.text,
                "source": w.source,
                "timestamp": w.timestamp,
            }
            for w in list(engine.witnesses)[: d.get("limit", 20)]
        ]
    },
}


async def _run_capability(capability_id: str, input_data: dict[str, Any]) -> Any:
    if capability_id == "platon.oracle@v1":
        from platon.oracle import generate_witness

        telem = input_data.get("telemetry") or engine.telemetry()
        if "event" in input_data:
            telem["event"] = input_data["event"]
        return await generate_witness(telem)

    if capability_id == "platon.ask@v1":
        from platon.ask import answer

        return await answer(
            input_data.get("question", ""), input_data.get("lang", "en"), engine
        )

    handler = _HANDLERS.get(capability_id)
    if handler is None:
        raise ValueError(f"Unknown capability: {capability_id}")
    return handler(input_data)


def _envelope(
    cap: dict[str, Any],
    capability_id: str,
    input_data: dict[str, Any],
    output: Any,
    latency_ms: float,
    success: bool = True,
) -> dict[str, Any]:
    timestamp = utc_now_z()
    receipt = _signer.sign_receipt(
        {
            "nonce": secrets.token_hex(8),
            "product_id": cap.get("product_id", "prod-platon"),
            "capability_id": capability_id,
            "price_usd": cap["price_per_call_usd"],
            "timestamp": timestamp,
            "success": success,
            "latency_ms": round(latency_ms, 2),
        }
    )
    return {
        "capability_id": capability_id,
        "output": output,
        "price_usd": cap["price_per_call_usd"],
        "provenance": {
            "source": "platon",
            "timestamp": timestamp,
            "input_hash": input_hash(input_data),
        },
        "receipt": receipt,
    }


async def invoke(capability_id: str, input_data: dict[str, Any]) -> dict[str, Any]:
    cap = _capability(capability_id)  # ValueError for unknown ids (handled upstream)
    start = time.perf_counter()
    success = True
    try:
        output = await _run_capability(capability_id, input_data)
    except Exception:
        success = False
        raise
    finally:
        latency_ms = (time.perf_counter() - start) * 1000.0
        metrics.record(capability_id, latency_ms, success)

    return _envelope(cap, capability_id, input_data, output, latency_ms)
