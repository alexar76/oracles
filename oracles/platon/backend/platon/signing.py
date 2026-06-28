"""Ed25519 signing for Platon AIMarket manifests, receipts and randomness.

The manifest canonical (4-field, with ``tools_hash``) and the receipt canonical
(7-field) match ``aimarket_hub/aimarket_hub/signing.py`` exactly, so signatures
produced here verify against the live hub at modelmarket.dev. (The 3-/5-field
forms in the protocol repo's test-vectors are stale and do NOT match the hub.)
"""

from __future__ import annotations

import base64
import contextlib
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from platon.config import settings

try:  # optional post-quantum signature (FIPS 204 ML-DSA-65), pure-Python
    from dilithium_py.ml_dsa import ML_DSA_65 as _MLDSA

    _PQ_LIB = True
except Exception:  # pragma: no cover - lib not installed
    _MLDSA = None
    _PQ_LIB = False


def pqc_available() -> bool:
    return _PQ_LIB


def _ensure_keypair(path: Path) -> tuple[bytes, bytes]:
    path.parent.mkdir(parents=True, exist_ok=True)
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    if path.exists():
        raw = path.read_bytes()
        if len(raw) == 64:
            return raw[:32], raw[32:]
        raise RuntimeError(f"Ed25519 key file {path} is corrupted (size={len(raw)})")

    priv = Ed25519PrivateKey.generate()
    pub = priv.public_key()
    seed = priv.private_bytes_raw()
    pub_bytes = pub.public_bytes_raw()
    path.write_bytes(seed + pub_bytes)
    with contextlib.suppress(OSError):
        os.chmod(path, 0o600)
    return seed, pub_bytes


def _seed_from_env() -> bytes | None:
    """Seed injected via env (e.g. from a secrets manager / KMS) — never on disk."""
    raw = os.environ.get("PLATON_SIGNING_SEED_B64")
    if not raw:
        return None
    seed = base64.b64decode(raw)
    if len(seed) != 32:
        raise RuntimeError("PLATON_SIGNING_SEED_B64 must decode to a 32-byte seed")
    return seed


def _load_or_make_pq(path: Path) -> tuple[bytes, bytes]:
    """Load or generate an ML-DSA-65 keypair (pk, sk), persisted hex-encoded."""
    if path.exists():
        pk_hex, sk_hex = path.read_text().split("\n")[:2]
        return bytes.fromhex(pk_hex), bytes.fromhex(sk_hex)
    pk, sk = _MLDSA.keygen()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{pk.hex()}\n{sk.hex()}\n")
    with contextlib.suppress(OSError):
        os.chmod(path, 0o600)
    return pk, sk


class Signer:
    def __init__(self, key_path: str | Path = "data/platon_signing_key") -> None:
        self.key_path = Path(key_path)
        env_seed = _seed_from_env()
        if env_seed is not None:
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

            self._seed = env_seed
            self._pub_bytes = (
                Ed25519PrivateKey.from_private_bytes(env_seed).public_key().public_bytes_raw()
            )
        else:
            self._seed, self._pub_bytes = _ensure_keypair(self.key_path)
        self._public_key_b64 = base64.b64encode(self._pub_bytes).decode()

        self._pq: tuple[bytes, bytes] | None = None
        if settings.pqc_enabled and _PQ_LIB:
            self._pq = _load_or_make_pq(Path(f"{self.key_path}_mldsa"))

    @property
    def public_key_b64(self) -> str:
        return self._public_key_b64

    # --- low-level ---------------------------------------------------------

    def sign_canonical(self, canonical: str) -> str:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

        sig = Ed25519PrivateKey.from_private_bytes(self._seed).sign(canonical.encode())
        return base64.b64encode(sig).decode()

    def sign_payload(self, canonical: str) -> dict[str, str]:
        """Full signature object. Always Ed25519; additionally ML-DSA-65 when PQC
        is enabled (hybrid). The Ed25519 fields are unchanged so existing verifiers
        and the hub keep working; PQC-aware verifiers also check ``pq_value``."""
        obj: dict[str, str] = {
            "algorithm": "ed25519",
            "public_key": self._public_key_b64,
            "value": self.sign_canonical(canonical),
        }
        if self._pq is not None:
            pk, sk = self._pq
            obj["pq_algorithm"] = "ml-dsa-65"
            obj["pq_public_key"] = base64.b64encode(pk).decode()
            obj["pq_value"] = base64.b64encode(_MLDSA.sign(sk, canonical.encode())).decode()
        return obj

    @staticmethod
    def verify(canonical: str, value_b64: str, public_key_b64: str) -> bool:
        """Verify a base64 Ed25519 signature over ``canonical`` (UTF-8 bytes)."""
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

        try:
            pub = Ed25519PublicKey.from_public_bytes(base64.b64decode(public_key_b64))
            pub.verify(base64.b64decode(value_b64), canonical.encode())
            return True
        except (InvalidSignature, ValueError):
            return False

    @staticmethod
    def verify_signature_object(
        canonical: str, sig: dict[str, Any], ed_public_key_b64: str | None = None
    ) -> bool:
        """Hybrid verify: Ed25519 must pass, and if a ``pq_value`` is present the
        ML-DSA signature must ALSO pass (both required → safe if either primitive
        holds, the point of a hybrid). Returns False if a PQ sig is present but the
        library is unavailable (cannot be checked → fail closed)."""
        ed_key = ed_public_key_b64 or sig.get("public_key")
        if not ed_key or not Signer.verify(canonical, sig.get("value", ""), ed_key):
            return False
        if sig.get("pq_value"):
            if not _PQ_LIB:
                return False
            try:
                pk = base64.b64decode(sig.get("pq_public_key", ""))
                return bool(_MLDSA.verify(pk, canonical.encode(), base64.b64decode(sig["pq_value"])))
            except Exception:
                return False
        return True

    # --- manifest (4-field canonical, matches the live hub) ----------------

    def manifest_canonical(self, manifest: dict[str, Any]) -> str:
        tools = manifest.get("tools", [])
        tools_hash = hashlib.sha256(
            json.dumps(tools, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()
        return (
            f"capabilities_count:{manifest.get('capabilities_count', 0)}"
            f"|generated_at:{manifest.get('generated_at', '')}"
            f"|protocol_version:{manifest.get('protocol_version', 'v1')}"
            f"|tools_hash:{tools_hash}"
        )

    def sign_manifest(self, manifest: dict[str, Any]) -> dict[str, str]:
        return self.sign_payload(self.manifest_canonical(manifest))

    def verify_manifest_signature(
        self, manifest: dict[str, Any], public_key_b64: str | None = None
    ) -> bool:
        sig = manifest.get("signature") or {}
        value = sig.get("value", "")
        key = public_key_b64 or sig.get("public_key") or self._public_key_b64
        return self.verify(self.manifest_canonical(manifest), value, key)

    # --- receipts (7-field canonical, matches the live hub) ----------------

    @staticmethod
    def receipt_canonical(receipt: dict[str, Any]) -> str:
        success = 1 if receipt.get("success", True) else 0
        return (
            f"nonce:{receipt.get('nonce', '')}"
            f"|product_id:{receipt.get('product_id', '')}"
            f"|capability_id:{receipt.get('capability_id', '')}"
            f"|price_usd:{receipt.get('price_usd', 0)}"
            f"|timestamp:{receipt.get('timestamp', '')}"
            f"|success:{success}"
            f"|latency_ms:{receipt.get('latency_ms', 0)}"
        )

    def sign_receipt(self, receipt: dict[str, Any]) -> dict[str, Any]:
        """Attach an Ed25519 signature (algorithm + value, no public_key — per
        the hub's receipt format) over the 7-field receipt canonical."""
        signed = dict(receipt)
        signed["signature"] = {
            "algorithm": "ed25519",
            "value": self.sign_canonical(self.receipt_canonical(receipt)),
        }
        return signed

    def verify_receipt(self, receipt: dict[str, Any], public_key_b64: str | None = None) -> bool:
        sig = receipt.get("signature") or {}
        key = public_key_b64 or self._public_key_b64
        body = {k: v for k, v in receipt.items() if k != "signature"}
        return self.verify(self.receipt_canonical(body), sig.get("value", ""), key)
