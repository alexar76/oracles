"""Aestus oracle spec — RSW time-lock puzzle capabilities on oracle-core."""

from __future__ import annotations

import os
from typing import Any

from oracle_core import Capability, OracleSpec

from aestus import rsw


def _seal(d: dict[str, Any]) -> dict[str, Any]:
    # The protocol layer does NOT validate input against input_schema, so the
    # handler enforces required fields and clamps T to [1, MAX_T] — otherwise a
    # caller could request an unbounded number of sequential squarings and pin a
    # CPU for an arbitrarily long time (exactly how Chronos clamps difficulty).
    data = d.get("data")
    if data is None:
        raise ValueError("missing 'data'")
    encoding = str(d.get("encoding", "utf8"))
    T = max(1, min(int(d.get("T", 1_000_000)), rsw.MAX_T))
    modulus_bits = int(d.get("modulus_bits", rsw.DEFAULT_MODULUS_BITS))
    return rsw.seal(str(data), T, encoding=encoding, modulus_bits=modulus_bits)


def _open(d: dict[str, Any]) -> dict[str, Any]:
    puzzle = d.get("puzzle")
    if puzzle is None:
        raise ValueError("missing 'puzzle'")
    return rsw.open_puzzle(puzzle)


def _verify(d: dict[str, Any]) -> dict[str, Any]:
    puzzle = d.get("puzzle")
    if puzzle is None:
        raise ValueError("missing 'puzzle'")
    b = d.get("b")
    if b is None:
        raise ValueError("missing 'b' (claimed result of the squarings)")
    return rsw.verify(puzzle, str(b))


_PUZZLE_SCHEMA = {
    "type": "object",
    "required": ["N", "a", "T", "ciphertext", "key_commitment"],
    "properties": {
        "scheme": {"type": "string"},
        "N": {"type": "string", "description": "Fresh RSA modulus N=p·q (factors burned at seal)."},
        "a": {"type": "string", "description": "Base; b = a^(2^T) mod N."},
        "T": {"type": "integer", "minimum": 1, "maximum": rsw.MAX_T},
        "ciphertext": {"type": "string", "description": "hex; plaintext XOR SHA256-CTR(key)."},
        "key_commitment": {"type": "string", "description": "SHA256 commitment binding the unlock value b."},
        "modulus_bits": {"type": "integer"},
        "encoding": {"type": "string", "enum": ["utf8", "hex"]},
    },
}


SPEC = OracleSpec(
    name="Aestus Time-Lock Oracle",
    product_id="prod-aestus",
    description=(
        "Rivest-Shamir-Wagner time-lock puzzles. SEAL data so NOBODY can open it "
        "before ~T sequential squarings of wall-clock have elapsed — then ANYONE "
        "can open it, with no trapdoor holder. Where Chronos proves the PAST "
        "elapsed, Aestus locks the FUTURE. Trustless by construction: each seal "
        "generates a FRESH RSA modulus N=p·q, derives the key by T sequential "
        "squarings (the honest slow path, NOT the φ(N) shortcut), and BURNS p,q,φ "
        "— so not even the oracle can open early. Honest tradeoff: because φ is "
        "burned, sealing costs the SAME T squarings as opening (seal-work == "
        "open-work); the φ shortcut would make sealing O(1) but would let the "
        "operator decrypt early, so we refuse to take it. Pure Python."
    ),
    public_url=os.environ.get("AESTUS_PUBLIC_URL", "http://localhost:9312"),
    categories=["time-lock", "timed-release", "delay-encryption", "agent-tooling"],
    signing_key_path=os.environ.get("AESTUS_SIGNING_KEY", "data/aestus_signing_key"),
    related=["https://github.com/alexar76"],
    capabilities=[
        Capability(
            capability_id="aestus.seal@v1",
            product_id="prod-aestus",
            description=(
                "Time-lock data: generate a fresh modulus N, compute b = a^(2^T) "
                "mod N via T sequential squarings, encrypt under SHA256(b), and "
                "burn the factorization. Returns a self-contained puzzle anyone can "
                "later open — the trapdoor is never returned (so the oracle cannot "
                "open early). Higher T = longer enforced delay before unlock."
            ),
            handler=_seal,
            input_schema={
                "type": "object",
                "required": ["data"],
                "properties": {
                    "data": {"type": "string", "minLength": 0,
                             "description": "Plaintext to seal (utf8 string, or hex if encoding='hex')."},
                    "encoding": {"type": "string", "enum": ["utf8", "hex"], "default": "utf8"},
                    "T": {"type": "integer", "minimum": 1, "maximum": rsw.MAX_T, "default": 1_000_000,
                          "description": "Sequential squarings = enforced delay before the puzzle opens."},
                    "modulus_bits": {"type": "integer", "minimum": rsw.MIN_MODULUS_BITS,
                                     "maximum": rsw.MAX_MODULUS_BITS, "default": rsw.DEFAULT_MODULUS_BITS},
                },
            },
            output_schema={
                "type": "object",
                "required": ["scheme", "N", "a", "T", "ciphertext", "key_commitment", "modulus_bits"],
                "properties": _PUZZLE_SCHEMA["properties"],
            },
            price_per_call_usd=0.006,
            p50_latency_ms=80,
            success_rate_30d=0.999,
        ),
        Capability(
            capability_id="aestus.open@v1",
            product_id="prod-aestus",
            description=(
                "Open a time-lock puzzle: redo the T sequential squarings to "
                "recover b = a^(2^T) mod N, derive the key, decrypt, and check b "
                "against the puzzle's key_commitment. Anyone can call this once "
                "enough time has elapsed — no trapdoor needed. Costs T squarings."
            ),
            handler=_open,
            input_schema={
                "type": "object",
                "required": ["puzzle"],
                "properties": {"puzzle": _PUZZLE_SCHEMA},
            },
            output_schema={
                "type": "object",
                "required": ["data", "b", "valid"],
                "properties": {
                    "data": {"type": "string"},
                    "b": {"type": "string", "description": "Recovered unlock value a^(2^T) mod N."},
                    "valid": {"type": "boolean", "description": "True iff b matches the key_commitment."},
                },
            },
            price_per_call_usd=0.01,
            p50_latency_ms=200,
            success_rate_30d=0.999,
        ),
        Capability(
            capability_id="aestus.verify@v1",
            product_id="prod-aestus",
            description=(
                "Cheap, trustless check that a claimed unlock value b is the correct "
                "result of the squarings: SHA256-commitment(b) == puzzle "
                "key_commitment, in ~one hash. Lets a worker who already opened the "
                "puzzle publish b so others confirm the unlock without redoing T "
                "squarings."
            ),
            handler=_verify,
            input_schema={
                "type": "object",
                "required": ["puzzle", "b"],
                "properties": {
                    "puzzle": _PUZZLE_SCHEMA,
                    "b": {"type": "string", "description": "Claimed result of the squarings (a^(2^T) mod N)."},
                },
            },
            output_schema={"type": "object", "required": ["valid"], "properties": {"valid": {"type": "boolean"}}},
            price_per_call_usd=0.001,
            p50_latency_ms=6,
            success_rate_30d=0.999,
        ),
    ],
)
