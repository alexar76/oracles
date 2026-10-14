"""Result-binding receipts for Murmuration.

The shared ``oracle_core`` signs a **7-field** receipt (nonce, product_id,
capability_id, price_usd, timestamp, success, latency_ms). That canonical form is
deliberately fixed so the signature also verifies against the live AIMarket hub —
but it does **not** cover the actual ``output`` or the ``input_hash``. On its own it
therefore only attests *"this oracle handled a call to capability X at time T"*, not
*"…and produced THIS result for THIS input"*. A relaying agent could swap the
``output`` field and the receipt would still verify — so the README promise that a
consumer can *"verify the result was produced by this oracle"* would not hold.

This module closes that gap **additively** — the same philosophy ``oracle_core``
already uses for post-quantum signatures (an extra ML-DSA signature attached
*alongside* Ed25519). We keep the hub-compatible 7-field signature untouched and
attach a second Ed25519 signature (``receipt["binding"]``) that cryptographically
ties this receipt — by its nonce and capability — to the exact ``input_hash`` and
``output_hash`` it was produced for. Nothing in ``oracle_core`` is modified: we
swap in a result-binding ``_envelope`` on the protocol via ``create_app``'s
``extra`` hook.

``verify_envelope`` performs the full end-to-end check a consumer needs:
recompute the output hash from the returned body, confirm it matches what the
receipt bound, and verify **both** signatures.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import types
from typing import Any

from oracle_core.protocol import input_hash, utc_now_z
from oracle_core.signing import Signer


def output_hash(output: Any) -> str:
    """SHA-256 over the canonical JSON of an output (mirrors ``input_hash``)."""
    return hashlib.sha256(
        json.dumps(output, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def binding_canonical(receipt: dict[str, Any]) -> str:
    """Canonical string the additive ``binding`` signature covers.

    Includes the receipt ``nonce`` (ties the binding to this one receipt, not a
    replayed one) and ``capability_id``, plus the input and output hashes.
    """
    return (
        f"nonce:{receipt.get('nonce', '')}"
        f"|capability_id:{receipt.get('capability_id', '')}"
        f"|input_hash:{receipt.get('input_hash', '')}"
        f"|output_hash:{receipt.get('output_hash', '')}"
    )


def _binding_envelope(self, cap, capability_id, input_data, output, latency_ms) -> dict[str, Any]:
    """Drop-in replacement for ``Protocol._envelope`` that binds input+output.

    Bound to a ``Protocol`` instance via :func:`install_result_binding`.
    """
    timestamp = utc_now_z()
    ih = input_hash(input_data)
    oh = output_hash(output)

    receipt: dict[str, Any] = {
        "nonce": secrets.token_hex(8),
        "product_id": cap.product_id,
        "capability_id": capability_id,
        "price_usd": cap.price_per_call_usd,
        "timestamp": timestamp,
        "success": True,
        "latency_ms": round(latency_ms, 2),
    }
    # (1) Hub-compatible 7-field signature. sign_receipt's canonical reads only the
    #     seven named keys via .get(), so adding input_hash/output_hash below does
    #     not alter it — the signature keeps verifying against the live hub.
    receipt = self.signer.sign_receipt(receipt)
    receipt["input_hash"] = ih
    receipt["output_hash"] = oh
    # (2) Additive result-binding signature (Ed25519, plus PQC when enabled).
    receipt["binding"] = self.signer.sign_payload(binding_canonical(receipt))

    return {
        "capability_id": capability_id,
        "output": output,
        "price_usd": cap.price_per_call_usd,
        "provenance": {
            "source": self.spec.product_id,
            "timestamp": timestamp,
            "input_hash": ih,
            "output_hash": oh,
        },
        "receipt": receipt,
    }


def install_result_binding(app, proto) -> None:
    """``create_app(extra=...)`` hook: bind outputs into every receipt.

    Replaces the protocol's ``_envelope`` with the result-binding version. The
    invoke route calls ``proto.invoke`` which calls ``self._envelope``, so the
    instance-level override takes effect for every call without touching
    ``oracle_core``.
    """
    proto._envelope = types.MethodType(_binding_envelope, proto)


def verify_envelope(env: dict[str, Any], public_key_b64: str | None = None) -> bool:
    """Full consumer-side verification of a Murmuration invoke envelope.

    Returns ``True`` only if the returned ``output`` is exactly the one the signed
    receipt was produced for. Pass ``public_key_b64`` (the oracle's key from its
    ``.well-known`` / manifest) to pin the signer — this is the security boundary.
    If omitted we fall back to the key advertised inside the binding, which proves
    internal consistency but not identity, so always pin in production.
    """
    if not isinstance(env, dict):
        return False
    receipt = env.get("receipt") or {}
    binding = receipt.get("binding") or {}
    key = public_key_b64 or binding.get("public_key")
    if not key:
        return False

    # (1) The output actually shipped must match the hash the receipt bound.
    if output_hash(env.get("output")) != receipt.get("output_hash"):
        return False
    # (2) Provenance input_hash must agree with the receipt's bound input_hash.
    prov = env.get("provenance") or {}
    if prov.get("input_hash") != receipt.get("input_hash"):
        return False
    # (3) Hub-compatible 7-field receipt signature must verify.
    body = {k: v for k, v in receipt.items() if k != "signature"}
    if not Signer.verify(
        Signer.receipt_canonical(body),
        (receipt.get("signature") or {}).get("value", ""),
        key,
    ):
        return False
    # (4) Additive binding signature (over nonce+capability+input+output) must verify.
    if not Signer.verify_signature_object(binding_canonical(receipt), binding, key):
        return False
    return True
