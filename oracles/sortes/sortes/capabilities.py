"""Sortes oracle spec — true ECVRF (RFC 9381) draw + offline verify on oracle-core."""

from __future__ import annotations

import os
import secrets
from pathlib import Path
from typing import Any

from oracle_core import Capability, OracleSpec

from sortes import vrf

# Largest output an unbounded caller may request. The protocol layer does NOT
# validate input against input_schema, so the handler clamps num_bytes itself —
# otherwise a caller could ask for an arbitrarily large stretched output and pin
# CPU/memory. 64 is beta's native length; anything above is SHA512-stretched.
MAX_NUM_BYTES = 64
# Cap alpha so a single draw cannot be made to hash megabytes (DoS guard).
MAX_ALPHA_BYTES = 4096

SUITE_STRING = "ECVRF-EDWARDS25519-SHA512-TAI"


# --- VRF keypair management ------------------------------------------------
def _load_or_create_sk() -> bytes:
    """Resolve the oracle's 32-byte VRF secret key.

    Order of precedence:
      1) SORTES_VRF_SK env (64 hex chars) — explicit, e.g. for reproducible deploys.
      2) A persisted key at SORTES_VRF_SK_PATH (default data/sortes_vrf_sk).
      3) Freshly generated, then persisted so the public key is stable across
         restarts (an oracle whose PK changes is useless — clients verify against it).
    The secret key NEVER leaves this module; only the public key is exposed.
    """
    env_sk = os.environ.get("SORTES_VRF_SK", "").strip()
    if env_sk:
        sk = bytes.fromhex(env_sk)
        if len(sk) != 32:
            raise ValueError("SORTES_VRF_SK must be 32 bytes (64 hex chars)")
        return sk

    path = Path(os.environ.get("SORTES_VRF_SK_PATH", "data/sortes_vrf_sk"))
    if path.exists():
        sk = bytes.fromhex(path.read_text().strip())
        if len(sk) == 32:
            return sk

    sk = secrets.token_bytes(32)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(sk.hex())
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
    except OSError:
        # Read-only FS (e.g. ephemeral test env): keep the in-memory key.
        pass
    return sk


_SK = _load_or_create_sk()
_PK = vrf.sk_to_pk(_SK)
PUBLIC_KEY_HEX = _PK.hex()


def _alpha_to_bytes(alpha: Any) -> bytes:
    """Interpret the client seed `alpha`. A 'hex:'-prefixed or pure-even-length
    hex string is decoded as raw bytes; otherwise the value is UTF-8 encoded.
    This keeps the wire format unambiguous while staying ergonomic for agents."""
    if alpha is None:
        raise ValueError("missing 'alpha'")
    if isinstance(alpha, (bytes, bytearray)):
        raw = bytes(alpha)
    else:
        s = str(alpha)
        if s.startswith("hex:"):
            raw = bytes.fromhex(s[4:])
        else:
            raw = s.encode("utf-8")
    if len(raw) > MAX_ALPHA_BYTES:
        raise ValueError(f"alpha too large (>{MAX_ALPHA_BYTES} bytes)")
    return raw


# --- handlers --------------------------------------------------------------
def _draw(d: dict[str, Any]) -> dict[str, Any]:
    alpha_raw = _alpha_to_bytes(d.get("alpha"))
    num_bytes = max(1, min(int(d.get("num_bytes", 32)), MAX_NUM_BYTES))

    # Dev/test escape hatch: a caller may pass an explicit 32-byte hex `sk` to make
    # the draw reproducible against published test vectors. Falls back to the
    # oracle's own persisted key, which is the production path.
    sk = _SK
    pk = _PK
    dev_sk = d.get("sk")
    if dev_sk is not None:
        sk = bytes.fromhex(str(dev_sk))
        if len(sk) != 32:
            raise ValueError("sk must be 32 bytes (64 hex chars)")
        pk = vrf.sk_to_pk(sk)

    pi = vrf.prove(sk, alpha_raw)
    gamma = pi[:32]
    c = pi[32:48]
    s = pi[48:80]
    beta = vrf.proof_to_hash(pi)
    assert beta is not None  # our own proof always decodes
    output = vrf.expand_output(beta, num_bytes)

    return {
        "suite": SUITE_STRING,
        "public_key": pk.hex(),
        "alpha": alpha_raw.hex(),
        "gamma": gamma.hex(),
        "c": c.hex(),
        "s": s.hex(),
        "pi": pi.hex(),
        "beta": beta.hex(),
        "output": output.hex(),
        "num_bytes": num_bytes,
    }


def _verify(d: dict[str, Any]) -> dict[str, Any]:
    try:
        pk = bytes.fromhex(str(d["public_key"]))
        pi = bytes.fromhex(str(d["pi"]))
        alpha_raw = _alpha_to_bytes(d.get("alpha"))
    except (KeyError, ValueError, TypeError) as exc:
        return {"valid": False, "beta": None, "error": f"malformed input: {exc}"}
    beta = vrf.verify(pk, alpha_raw, pi)
    if beta is None:
        return {"valid": False, "beta": None}
    return {"valid": True, "beta": beta.hex()}


SPEC = OracleSpec(
    name="Sortes VRF Oracle",
    product_id="prod-sortes",
    description=(
        "Sortes draws lots you can verify. A true ECVRF (RFC 9381, suite "
        "ECVRF-EDWARDS25519-SHA512-TAI over edwards25519): the output beta is a "
        "uniform pseudorandom string cryptographically BOUND to the oracle's public "
        "key and the client's input alpha, and anyone can verify it OFFLINE from the "
        "80-byte proof. Unlike a trusted beacon the oracle cannot grind the result — "
        "for a fixed (public_key, alpha) exactly one valid output exists. "
        f"VRF public key: {PUBLIC_KEY_HEX}."
    ),
    public_url=os.environ.get("SORTES_PUBLIC_URL", "http://localhost:9310"),
    categories=["verifiable-randomness", "vrf", "rfc9381", "sortition", "agent-tooling"],
    signing_key_path=os.environ.get("SORTES_SIGNING_KEY", "data/sortes_signing_key"),
    related=["https://github.com/alexar76"],
    capabilities=[
        Capability(
            capability_id="sortes.draw@v1",
            product_id="prod-sortes",
            description=(
                "Draw verifiable randomness for an input alpha. Computes the ECVRF "
                "proof pi and output beta with the oracle's secret key (never returned), "
                "binding the result to (public_key, alpha). Returns the public_key, the "
                "proof components (gamma, c, s, pi), beta, and `output` (num_bytes of "
                "uniform randomness). Anyone can re-verify offline with sortes.verify@v1."
            ),
            handler=_draw,
            input_schema={
                "type": "object",
                "required": ["alpha"],
                "properties": {
                    "alpha": {
                        "type": "string",
                        "description": "Client seed/message. UTF-8 by default; prefix 'hex:' for raw bytes.",
                    },
                    "num_bytes": {
                        "type": "integer", "minimum": 1, "maximum": MAX_NUM_BYTES, "default": 32,
                        "description": "Length of the derived uniform `output` (beta is 64 bytes).",
                    },
                },
            },
            output_schema={
                "type": "object",
                "required": ["public_key", "alpha", "pi", "beta", "output", "suite"],
                "properties": {
                    "suite": {"type": "string"},
                    "public_key": {"type": "string"},
                    "alpha": {"type": "string"},
                    "gamma": {"type": "string"},
                    "c": {"type": "string"},
                    "s": {"type": "string"},
                    "pi": {"type": "string"},
                    "beta": {"type": "string"},
                    "output": {"type": "string"},
                    "num_bytes": {"type": "integer"},
                },
            },
            price_per_call_usd=0.006,
            p50_latency_ms=8,
            success_rate_30d=0.999,
        ),
        Capability(
            capability_id="sortes.verify@v1",
            product_id="prod-sortes",
            description=(
                "Verify an ECVRF proof offline and trustlessly. Given (public_key, "
                "alpha, pi) returns valid:true with the canonical beta iff the proof is "
                "the unique correct VRF output for that (public_key, alpha); otherwise "
                "valid:false. Needs no trust in the oracle."
            ),
            handler=_verify,
            input_schema={
                "type": "object",
                "required": ["public_key", "alpha", "pi"],
                "properties": {
                    "public_key": {"type": "string", "description": "VRF public key (32-byte hex)."},
                    "alpha": {"type": "string", "description": "The input that was drawn (UTF-8 or 'hex:' raw)."},
                    "pi": {"type": "string", "description": "The 80-byte ECVRF proof (hex)."},
                },
            },
            output_schema={
                "type": "object",
                "required": ["valid"],
                "properties": {
                    "valid": {"type": "boolean"},
                    "beta": {"type": ["string", "null"]},
                },
            },
            price_per_call_usd=0.001,
            p50_latency_ms=6,
            success_rate_30d=0.999,
        ),
    ],
)
