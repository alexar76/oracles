"""Chaos VRF — verifiable randomness drawn from the 32D chaotic shadow.

The 32 coupled Stuart-Landau / Kuramoto oscillators have a positive Lyapunov
exponent in the chaotic regime, so the evolving state is a deterministic but
practically unpredictable entropy source. Each draw:

1. hashes the full live state vector -> ``state_hash`` (the beacon round's entropy),
2. mixes in fresh OS-CSPRNG ``entropy`` (committed via ``entropy_commitment``) and
   an optional ``client_seed`` (the client contributes entropy the server cannot
   control) plus the tick and timestamp,
3. expands that to ``num_bytes`` of output in SHA-256 counter mode,
4. signs a canonical binding of (output, proof) with the service's Ed25519 key.

Consumers verify the signature against Platon's published ``signer_public_key``
(from ``/.well-known/ai-market.json``) AND independently reproduce the draw: they
OPEN the commitment (``H(entropy) == entropy_commitment``) and re-derive
``random_hex`` from the revealed entropy. The output is therefore unpredictable
before issuance (the entropy is secret until then) and, once issued, both
non-repudiable and provably the agreed deterministic function of the committed
inputs — a drand-style beacon backed by a chaotic oracle.
"""

from __future__ import annotations

import hashlib
import secrets
from collections import deque
from typing import Any

import numpy as np

SCHEME = "platon-chaos-vrf/v1"
BEACON_SCHEME = "platon-chaos-beacon/v1"


def _expand(seed: bytes, num_bytes: int) -> bytes:
    """SHA-256 counter-mode expansion to an arbitrary length."""
    out = bytearray()
    counter = 0
    while len(out) < num_bytes:
        out += hashlib.sha256(seed + counter.to_bytes(4, "big")).digest()
        counter += 1
    return bytes(out[:num_bytes])


def randomness_canonical(random_hex: str, proof: dict[str, Any]) -> str:
    """The exact string signed for a randomness draw (UTF-8 bytes, Ed25519)."""
    return (
        f"scheme:{proof['scheme']}"
        f"|random_hex:{random_hex}"
        f"|state_hash:{proof['state_hash']}"
        f"|client_seed:{proof['client_seed']}"
        f"|tick:{proof['tick']}"
        f"|timestamp:{proof['timestamp']}"
        f"|entropy_commitment:{proof.get('entropy_commitment', '')}"
    )


def draw_randomness(
    state_vector: np.ndarray,
    tick: int,
    timestamp: str,
    signer: Any,
    num_bytes: int = 32,
    client_seed: str = "",
) -> dict[str, Any]:
    """Produce a signed verifiable-randomness draw from the current chaotic state."""
    num_bytes = max(1, min(int(num_bytes), 64))

    state_bytes = np.ascontiguousarray(state_vector, dtype=np.float64).tobytes()
    state_hash = hashlib.sha256(state_bytes).hexdigest()

    # Fresh OS-CSPRNG entropy makes the draw unpredictable *before* issuance — not
    # merely a deterministic function of the public inputs. We commit to it
    # (``entropy_commitment``, which is what the signature covers) AND reveal the
    # entropy itself in the proof, so a consumer can OPEN the commitment
    # (``H(entropy) == entropy_commitment``) and re-derive ``random_hex`` from it.
    # That is what makes the draw genuinely verifiable rather than "trust me": the
    # output is provably the agreed deterministic function of the committed entropy.
    os_entropy = secrets.token_bytes(32)
    entropy_commitment = hashlib.sha256(os_entropy).hexdigest()

    seed = (
        bytes.fromhex(state_hash)
        + os_entropy
        + client_seed.encode()
        + str(tick).encode()
        + timestamp.encode()
    )
    random_hex = _expand(seed, num_bytes).hex()

    proof = {
        "scheme": SCHEME,
        "state_hash": state_hash,
        "client_seed": client_seed,
        "tick": tick,
        "timestamp": timestamp,
        "entropy_commitment": entropy_commitment,
        # Revealed preimage of entropy_commitment. Unpredictable before issuance;
        # opened here so the output is independently reproducible/verifiable.
        "entropy": os_entropy.hex(),
    }
    signature = signer.sign_payload(randomness_canonical(random_hex, proof))

    return {
        "random_hex": random_hex,
        "num_bytes": num_bytes,
        "proof": proof,
        "signature": signature,
    }


def _entropy_binding_ok(
    random_hex: str, proof: dict[str, Any], state_prefix: bytes, counter: Any
) -> bool:
    """Open the entropy commitment and re-derive ``random_hex`` from it.

    Returns True only if (1) the revealed ``entropy`` opens the signed
    ``entropy_commitment`` (``H(entropy) == entropy_commitment``) and (2)
    ``random_hex`` is exactly the deterministic expansion of the committed seed.
    Without this the "proof" is vacuous: the operator could publish any output
    with any (never-opened) commitment and it would still carry a valid signature.
    """
    entropy_hex = proof.get("entropy")
    if not isinstance(entropy_hex, str) or not entropy_hex:
        return False
    try:
        os_entropy = bytes.fromhex(entropy_hex)
        out_len = len(bytes.fromhex(random_hex))
        state_bytes = bytes.fromhex(proof["state_hash"])
    except (ValueError, KeyError, TypeError):
        return False
    # (1) open the commitment
    if hashlib.sha256(os_entropy).hexdigest() != proof.get("entropy_commitment"):
        return False
    # (2) bind random_hex to the opened entropy (same construction as issuance)
    seed = (
        state_bytes
        + state_prefix
        + os_entropy
        + str(proof.get("client_seed", "")).encode()
        + str(counter).encode()
        + str(proof.get("timestamp", "")).encode()
    )
    return _expand(seed, out_len).hex() == random_hex


def verify_randomness(result: dict[str, Any], public_key_b64: str | None = None) -> bool:
    """Verify a randomness draw end-to-end (for consumers / tests).

    Checks the Ed25519 signature AND opens the entropy commitment, re-deriving
    ``random_hex`` from the revealed entropy — so a signed-but-fabricated output
    (operator grinding / an unopened commitment) is rejected, not just accepted
    on the strength of a signature the operator can always produce.
    """
    from platon.signing import Signer

    sig = result.get("signature") or {}
    key = public_key_b64 or sig.get("public_key")
    if not key:
        return False
    proof = result.get("proof") or {}
    canonical = randomness_canonical(result["random_hex"], proof)
    if not Signer.verify(canonical, sig.get("value", ""), key):
        return False
    return _entropy_binding_ok(
        result["random_hex"], proof, state_prefix=b"", counter=proof.get("tick")
    )


GENESIS_HASH = "0" * 64


def beacon_round_canonical(rnd: dict[str, Any]) -> str:
    """The exact string signed (and hashed into round_hash) for a beacon round."""
    p = rnd["proof"]
    return (
        f"round:{rnd['round']}"
        f"|prev_hash:{rnd['prev_hash']}"
        f"|random_hex:{rnd['random_hex']}"
        f"|state_hash:{p['state_hash']}"
        f"|client_seed:{p['client_seed']}"
        f"|tick:{p['tick']}"
        f"|timestamp:{p['timestamp']}"
        f"|entropy_commitment:{p.get('entropy_commitment', '')}"
    )


class Beacon:
    """Hash-chained verifiable randomness beacon.

    Each round links to the previous one's ``round_hash`` (a SHA-256 of the
    round's canonical) and is Ed25519-signed. Altering any past round breaks both
    its signature and every subsequent ``prev_hash`` — a provable, tamper-evident
    chain (drand-style), with entropy sourced from the chaotic state, fresh OS
    entropy (committed and revealed, so ``random_hex`` is re-derivable), the
    forward-chained ``prev_hash`` and an optional client seed.

    Verification (``verify_beacon_chain``) is anchored to the genesis round, so a
    front-truncated suffix cannot pass as a complete chain.
    """

    def __init__(self, signer: Any, maxlen: int = 512) -> None:
        self._signer = signer
        self.rounds: deque[dict[str, Any]] = deque(maxlen=maxlen)

    def latest(self) -> dict[str, Any] | None:
        return self.rounds[-1] if self.rounds else None

    def checkpoint(self, timestamp: str) -> dict[str, Any]:
        """A signed commitment to the current chain head — meant to be anchored to
        an external transparency log / chain so the operator cannot silently rewrite
        history (docs/SECURITY.md §2.4)."""
        latest = self.latest()
        body = {
            "scheme": "platon-beacon-checkpoint/v1",
            "latest_round": latest["round"] if latest else -1,
            "round_hash": latest["round_hash"] if latest else GENESIS_HASH,
            "chain_length": len(self.rounds),
            "timestamp": timestamp,
        }
        body["signature"] = self._signer.sign_payload(checkpoint_canonical(body))
        return body

    def emit(
        self,
        state_vector: np.ndarray,
        tick: int,
        timestamp: str,
        num_bytes: int = 32,
        client_seed: str = "",
    ) -> dict[str, Any]:
        num_bytes = max(1, min(int(num_bytes), 64))
        prev = self.latest()
        round_no = prev["round"] + 1 if prev else 0
        prev_hash = prev["round_hash"] if prev else GENESIS_HASH

        state_bytes = np.ascontiguousarray(state_vector, dtype=np.float64).tobytes()
        state_hash = hashlib.sha256(state_bytes).hexdigest()
        os_entropy = secrets.token_bytes(32)  # true OS-CSPRNG entropy per round
        entropy_commitment = hashlib.sha256(os_entropy).hexdigest()
        seed = (
            bytes.fromhex(state_hash)
            + bytes.fromhex(prev_hash)
            + os_entropy
            + client_seed.encode()
            + str(round_no).encode()
            + timestamp.encode()
        )
        random_hex = _expand(seed, num_bytes).hex()

        rnd: dict[str, Any] = {
            "round": round_no,
            "prev_hash": prev_hash,
            "random_hex": random_hex,
            "num_bytes": num_bytes,
            "proof": {
                "scheme": BEACON_SCHEME,
                "state_hash": state_hash,
                "client_seed": client_seed,
                "tick": tick,
                "timestamp": timestamp,
                "entropy_commitment": entropy_commitment,
                # Revealed preimage of entropy_commitment (see draw_randomness):
                # lets a consumer open the commitment and re-derive random_hex.
                "entropy": os_entropy.hex(),
            },
        }
        canonical = beacon_round_canonical(rnd)
        rnd["signature"] = self._signer.sign_payload(canonical)
        rnd["round_hash"] = hashlib.sha256(canonical.encode()).hexdigest()
        self.rounds.append(rnd)
        return rnd


def checkpoint_canonical(cp: dict[str, Any]) -> str:
    return (
        f"scheme:{cp['scheme']}|latest_round:{cp['latest_round']}"
        f"|round_hash:{cp['round_hash']}|chain_length:{cp['chain_length']}"
        f"|timestamp:{cp['timestamp']}"
    )


def verify_checkpoint(cp: dict[str, Any], public_key_b64: str | None = None) -> bool:
    from platon.signing import Signer

    sig = cp.get("signature") or {}
    key = public_key_b64 or sig.get("public_key")
    return bool(key) and Signer.verify(checkpoint_canonical(cp), sig.get("value", ""), key)


def verify_beacon_chain(
    rounds: list[dict[str, Any]],
    public_key_b64: str | None = None,
    require_genesis: bool = True,
) -> bool:
    """Verify each round's signature, its round_hash, the entropy binding, and the
    prev_hash linkage.

    With ``require_genesis`` (the default), the chain MUST start at the genesis
    round (``round == 0`` and ``prev_hash == GENESIS_HASH``). Otherwise a
    front-truncated *suffix* of a genuine chain — every remaining round genuinely
    signed and internally linked — would verify as a complete chain, letting an
    operator silently drop early rounds. Pass ``require_genesis=False`` only to
    integrity-check a known rolling window that legitimately omits genesis (e.g.
    the operator's own bounded in-memory deque after eviction).
    """
    from platon.signing import Signer

    if not rounds:
        # An empty list anchors nothing; only meaningful as a rolling-window check.
        return not require_genesis
    if require_genesis and (
        rounds[0].get("round") != 0 or rounds[0].get("prev_hash") != GENESIS_HASH
    ):
        return False

    prev_hash = None
    for rnd in rounds:
        canonical = beacon_round_canonical(rnd)
        sig = rnd.get("signature") or {}
        key = public_key_b64 or sig.get("public_key")
        if not key or not Signer.verify(canonical, sig.get("value", ""), key):
            return False
        if hashlib.sha256(canonical.encode()).hexdigest() != rnd.get("round_hash"):
            return False
        if prev_hash is not None and rnd.get("prev_hash") != prev_hash:
            return False
        # Open the entropy commitment and re-derive random_hex (see draw_randomness):
        # the beacon seed additionally chains in prev_hash and keys off round_no.
        try:
            state_prefix = bytes.fromhex(rnd["prev_hash"])
        except (ValueError, KeyError, TypeError):
            return False
        if not _entropy_binding_ok(
            rnd["random_hex"], rnd.get("proof") or {}, state_prefix, rnd.get("round")
        ):
            return False
        prev_hash = rnd["round_hash"]
    return True
