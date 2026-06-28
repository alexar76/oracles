"""Commit-reveal randomness — bias-resistant against the provider itself.

Closes the "last-look grinding" gap (docs/SECURITY.md §2.3): the server commits
to — and signs — a commitment to a *secret preimage* BEFORE the client supplies
its seed. The output is then fixed as ``H(preimage ‖ client_seed)``. The server
cannot grind (its preimage is locked by the signed, timestamped commitment) and
the client cannot grind (it never sees the preimage before choosing its seed).
Neither party alone controls the result, and the whole exchange is verifiable.
"""

from __future__ import annotations

import hashlib
import secrets
from collections import OrderedDict
from typing import Any

import numpy as np

from platon.randomness import _expand

SCHEME = "platon-commit-reveal/v1"


def commit_canonical(round_no: int, commitment: str, committed_at: str) -> str:
    return f"scheme:{SCHEME}|round:{round_no}|commitment:{commitment}|committed_at:{committed_at}"


def reveal_canonical(rec: dict[str, Any]) -> str:
    return (
        f"scheme:{SCHEME}|round:{rec['round']}|commitment:{rec['commitment']}"
        f"|preimage:{rec['preimage']}|client_seed:{rec['client_seed']}"
        f"|random_hex:{rec['random_hex']}|revealed_at:{rec['revealed_at']}"
    )


def _state_hash(state_vector: np.ndarray) -> str:
    return hashlib.sha256(
        np.ascontiguousarray(state_vector, dtype=np.float64).tobytes()
    ).hexdigest()


class CommitRevealBeacon:
    def __init__(self, signer: Any, maxlen: int = 512) -> None:
        self._signer = signer
        self._round = 0
        self._pending: "OrderedDict[int, dict[str, Any]]" = OrderedDict()
        self._maxlen = maxlen

    def commit(self, state_vector: np.ndarray, tick: int, committed_at: str) -> dict[str, Any]:
        round_no = self._round
        self._round += 1
        server_nonce = secrets.token_hex(16)
        # secret preimage — NOT revealed until reveal()
        preimage = f"{_state_hash(state_vector)}:{server_nonce}:{round_no}:{tick}:{committed_at}"
        commitment = hashlib.sha256(preimage.encode()).hexdigest()

        public = {
            "scheme": SCHEME,
            "round": round_no,
            "commitment": commitment,
            "committed_at": committed_at,
        }
        public["signature"] = self._signer.sign_payload(
            commit_canonical(round_no, commitment, committed_at)
        )

        self._pending[round_no] = {
            **public,
            "_preimage": preimage,
            "_consumed": False,
        }
        while len(self._pending) > self._maxlen:
            self._pending.popitem(last=False)
        return public

    def reveal(
        self, round_no: int, client_seed: str, revealed_at: str, num_bytes: int = 32
    ) -> dict[str, Any]:
        entry = self._pending.get(round_no)
        if entry is None:
            raise ValueError(f"Unknown or expired commit round: {round_no}")
        if entry["_consumed"]:
            raise ValueError(f"Commit round already revealed: {round_no}")
        num_bytes = max(1, min(int(num_bytes), 64))

        preimage = entry["_preimage"]
        seed = hashlib.sha256(f"{preimage}:{client_seed}".encode()).digest()
        random_hex = _expand(seed, num_bytes).hex()

        rec = {
            "scheme": SCHEME,
            "round": round_no,
            "commitment": entry["commitment"],
            "committed_at": entry["committed_at"],
            "commit_signature": entry["signature"],
            "preimage": preimage,
            "client_seed": client_seed,
            "random_hex": random_hex,
            "num_bytes": num_bytes,
            "revealed_at": revealed_at,
        }
        rec["signature"] = self._signer.sign_payload(reveal_canonical(rec))
        entry["_consumed"] = True
        return rec


def verify_reveal(rec: dict[str, Any], public_key_b64: str | None = None) -> bool:
    """Verify a reveal end-to-end: commitment binding, output derivation, and both
    signatures (commit was signed before the client seed; reveal matches it)."""
    from platon.signing import Signer

    # 1. commitment binds the revealed preimage
    if hashlib.sha256(rec["preimage"].encode()).hexdigest() != rec["commitment"]:
        return False
    # 2. output is the agreed function of preimage + client_seed
    seed = hashlib.sha256(f"{rec['preimage']}:{rec['client_seed']}".encode()).digest()
    if _expand(seed, rec["num_bytes"]).hex() != rec["random_hex"]:
        return False
    # 3. signatures
    commit_sig = rec.get("commit_signature") or {}
    reveal_sig = rec.get("signature") or {}
    ckey = public_key_b64 or commit_sig.get("public_key")
    rkey = public_key_b64 or reveal_sig.get("public_key")
    if not ckey or not rkey:
        return False
    commit_ok = Signer.verify(
        commit_canonical(rec["round"], rec["commitment"], rec["committed_at"]),
        commit_sig.get("value", ""),
        ckey,
    )
    reveal_ok = Signer.verify(reveal_canonical(rec), reveal_sig.get("value", ""), rkey)
    return commit_ok and reveal_ok
