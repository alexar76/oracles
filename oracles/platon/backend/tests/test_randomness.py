import hashlib

import numpy as np
import pytest

from platon.randomness import (
    GENESIS_HASH,
    Beacon,
    beacon_round_canonical,
    draw_randomness,
    randomness_canonical,
    verify_beacon_chain,
    verify_checkpoint,
    verify_randomness,
)
from platon.signing import Signer


def _other_first_byte(hex_str: str) -> str:
    """Return `hex_str` with its first byte changed to one it definitely was not.

    The tamper tests below used to write a literal `"00" + rest` (or `"ff" + rest`).
    One run in 256 the draw already began with that byte, so the "tampered" value was
    byte-identical to the original, verification correctly returned True, and the suite
    reported a failure — on the one assertion that must never cry wolf. Harmless when
    draws were deterministic; a fresh coin flip every run since they take OS entropy.
    """
    return ("01" if hex_str[:2] == "00" else "00") + hex_str[2:]


def _flip_hex_prefix(h: str) -> str:
    """Return a same-length hex string guaranteed to differ from ``h``."""
    return ("00" if not h.startswith("00") else "11") + h[2:]


@pytest.fixture
def signer(tmp_path):
    return Signer(tmp_path / "key")


class TestChaosVRF:
    def test_draw_is_signed_and_verifies(self, signer):
        v = np.random.default_rng(1).normal(size=64)
        r = draw_randomness(v, tick=10, timestamp="2026-06-13T10:00:00Z", signer=signer)
        assert len(bytes.fromhex(r["random_hex"])) == 32
        assert verify_randomness(r, signer.public_key_b64) is True

    def test_num_bytes_clamped_and_honored(self, signer):
        v = np.zeros(64)
        r = draw_randomness(v, 1, "2026-06-13T10:00:00Z", signer, num_bytes=8)
        assert r["num_bytes"] == 8
        assert len(bytes.fromhex(r["random_hex"])) == 8
        big = draw_randomness(v, 1, "2026-06-13T10:00:00Z", signer, num_bytes=999)
        assert big["num_bytes"] == 64

    def test_different_state_gives_different_output(self, signer):
        v1 = np.random.default_rng(1).normal(size=64)
        v2 = np.random.default_rng(2).normal(size=64)
        ts = "2026-06-13T10:00:00Z"
        r1 = draw_randomness(v1, 5, ts, signer, client_seed="x")
        r2 = draw_randomness(v2, 5, ts, signer, client_seed="x")
        assert r1["random_hex"] != r2["random_hex"]

    def test_client_seed_changes_output(self, signer):
        v = np.random.default_rng(3).normal(size=64)
        ts = "2026-06-13T10:00:00Z"
        a = draw_randomness(v, 5, ts, signer, client_seed="alice")
        b = draw_randomness(v, 5, ts, signer, client_seed="bob")
        assert a["random_hex"] != b["random_hex"]

    def test_tampered_draw_is_rejected(self, signer):
        v = np.random.default_rng(4).normal(size=64)
        r = draw_randomness(v, 7, "2026-06-13T10:00:00Z", signer)
        tampered = dict(r)
        tampered["random_hex"] = _other_first_byte(r["random_hex"])
        assert verify_randomness(tampered, signer.public_key_b64) is False

    def test_canonical_is_stable(self, signer):
        v = np.zeros(64)
        r = draw_randomness(v, 1, "2026-06-13T10:00:00Z", signer)
        c = randomness_canonical(r["random_hex"], r["proof"])
        assert c.startswith("scheme:platon-chaos-vrf/v1|random_hex:")

    def test_unpredictable_with_os_entropy(self, signer):
        # Identical public inputs MUST now yield different output (true OS entropy),
        # and each draw commits to its entropy and stays signature-verifiable.
        v = np.zeros(64)
        a = draw_randomness(v, 7, "2026-06-13T10:00:00Z", signer, client_seed="same")
        b = draw_randomness(v, 7, "2026-06-13T10:00:00Z", signer, client_seed="same")
        assert a["random_hex"] != b["random_hex"]
        assert len(a["proof"]["entropy_commitment"]) == 64
        assert verify_randomness(a, signer.public_key_b64) is True

    def test_proof_reveals_and_opens_entropy(self, signer):
        # The commitment must actually be openable: entropy is revealed and hashes
        # to entropy_commitment (otherwise the "commitment" proves nothing).
        v = np.random.default_rng(11).normal(size=64)
        r = draw_randomness(v, 3, "2026-06-13T10:00:00Z", signer)
        entropy = r["proof"]["entropy"]
        assert (
            hashlib.sha256(bytes.fromhex(entropy)).hexdigest()
            == r["proof"]["entropy_commitment"]
        )

    def test_verify_opens_commitment(self, signer):
        # Regression: a draw whose revealed entropy does NOT open the signed
        # commitment must be rejected. The signature stays valid (entropy is not
        # part of the signed canonical), so a signature-only verifier would pass it.
        v = np.random.default_rng(12).normal(size=64)
        r = draw_randomness(v, 3, "2026-06-13T10:00:00Z", signer)
        bad = {**r, "proof": {**r["proof"]}}
        bad["proof"]["entropy"] = _flip_hex_prefix(r["proof"]["entropy"])
        assert bad["signature"] == r["signature"]  # signature untouched & valid
        assert verify_randomness(bad, signer.public_key_b64) is False

    def test_verify_binds_random_hex_to_committed_entropy(self, signer):
        # Regression: the core "vacuous proof" attack. The operator publishes an
        # output NOT derived from the committed entropy but signs it with the real
        # key (which it always can). Verify must re-derive random_hex from the
        # opened entropy and reject the fabricated value.
        v = np.random.default_rng(13).normal(size=64)
        r = draw_randomness(v, 3, "2026-06-13T10:00:00Z", signer)
        forged_proof = {**r["proof"]}
        forged = {**r, "proof": forged_proof}
        forged["random_hex"] = _flip_hex_prefix(r["random_hex"])
        # re-sign so the signature is genuinely valid for the fabricated output
        forged["signature"] = signer.sign_payload(
            randomness_canonical(forged["random_hex"], forged_proof)
        )
        assert Signer.verify(
            randomness_canonical(forged["random_hex"], forged_proof),
            forged["signature"]["value"],
            signer.public_key_b64,
        )  # signature really does verify — only the entropy binding should reject it
        assert verify_randomness(forged, signer.public_key_b64) is False


class TestBeacon:
    def test_chain_links_and_verifies(self, signer):
        beacon = Beacon(signer)
        v = np.random.default_rng(1).normal(size=64)
        for i in range(5):
            beacon.emit(v, tick=i, timestamp="2026-06-13T10:00:00Z", client_seed=str(i))
        rounds = list(beacon.rounds)
        assert [r["round"] for r in rounds] == [0, 1, 2, 3, 4]
        assert rounds[0]["prev_hash"] == GENESIS_HASH
        assert rounds[1]["prev_hash"] == rounds[0]["round_hash"]
        assert verify_beacon_chain(rounds, signer.public_key_b64) is True

    def test_tampering_breaks_chain(self, signer):
        beacon = Beacon(signer)
        v = np.zeros(64)
        for i in range(3):
            beacon.emit(v, tick=i, timestamp="2026-06-13T10:00:00Z")
        rounds = list(beacon.rounds)
        rounds[1]["random_hex"] = _other_first_byte(rounds[1]["random_hex"])
        assert verify_beacon_chain(rounds, signer.public_key_b64) is False

    def test_broken_link_rejected(self, signer):
        beacon = Beacon(signer)
        v = np.zeros(64)
        for i in range(3):
            beacon.emit(v, tick=i, timestamp="2026-06-13T10:00:00Z")
        rounds = list(beacon.rounds)
        rounds[2]["prev_hash"] = "0" * 64  # wrong link
        assert verify_beacon_chain(rounds, signer.public_key_b64) is False

    def test_front_truncated_chain_rejected(self, signer):
        # Regression: dropping early rounds (keeping genuine, internally-linked
        # later ones) must NOT verify as a complete chain — verification is
        # anchored to genesis (round 0, prev_hash == GENESIS_HASH).
        beacon = Beacon(signer)
        v = np.random.default_rng(9).normal(size=64)
        for i in range(4):
            beacon.emit(v, tick=i, timestamp="2026-06-13T10:00:00Z", client_seed=str(i))
        rounds = list(beacon.rounds)
        assert verify_beacon_chain(rounds, signer.public_key_b64) is True

        suffix = rounds[1:]  # genesis removed
        assert suffix[0]["round"] == 1
        assert verify_beacon_chain(suffix, signer.public_key_b64) is False
        # explicit rolling-window mode still accepts a valid (linked) window
        assert (
            verify_beacon_chain(suffix, signer.public_key_b64, require_genesis=False)
            is True
        )

    def test_forged_genesis_prev_hash_rejected(self, signer):
        # A round claiming to be genesis but with a non-GENESIS prev_hash is rejected.
        beacon = Beacon(signer)
        beacon.emit(np.zeros(64), tick=0, timestamp="2026-06-13T10:00:00Z")
        rounds = list(beacon.rounds)
        forged = {**rounds[0], "prev_hash": "ab" * 32}
        # keep signature/round_hash self-consistent so only the genesis check bites
        canonical = beacon_round_canonical(forged)
        forged["signature"] = signer.sign_payload(canonical)
        forged["round_hash"] = hashlib.sha256(canonical.encode()).hexdigest()
        assert verify_beacon_chain([forged], signer.public_key_b64) is False

    def test_beacon_entropy_commitment_opened(self, signer):
        # Regression: each beacon round's entropy must open its commitment and
        # re-derive random_hex, exactly like a single draw.
        beacon = Beacon(signer)
        beacon.emit(np.zeros(64), tick=0, timestamp="2026-06-13T10:00:00Z")
        rounds = list(beacon.rounds)
        assert verify_beacon_chain(rounds, signer.public_key_b64) is True
        bad = [{**rounds[0], "proof": {**rounds[0]["proof"]}}]
        bad[0]["proof"]["entropy"] = _flip_hex_prefix(rounds[0]["proof"]["entropy"])
        assert verify_beacon_chain(bad, signer.public_key_b64) is False

    def test_signed_checkpoint_verifies(self, signer):
        beacon = Beacon(signer)
        beacon.emit(np.zeros(64), tick=0, timestamp="2026-06-13T10:00:00Z")
        cp = beacon.checkpoint("2026-06-13T10:00:10Z")
        assert cp["latest_round"] == 0 and cp["chain_length"] == 1
        assert verify_checkpoint(cp, signer.public_key_b64) is True
        cp["round_hash"] = "0" * 64  # tamper
        assert verify_checkpoint(cp, signer.public_key_b64) is False


class TestCommitReveal:
    def _beacon(self, signer):
        from platon.commit_reveal import CommitRevealBeacon

        return CommitRevealBeacon(signer)

    def test_commit_reveal_verifies(self, signer):
        from platon.commit_reveal import verify_reveal

        b = self._beacon(signer)
        v = np.zeros(64)
        c = b.commit(v, tick=1, committed_at="2026-06-13T10:00:00Z")
        assert "signature" in c and "preimage" not in c  # preimage stays secret at commit
        r = b.reveal(c["round"], client_seed="agent-42", revealed_at="2026-06-13T10:00:05Z")
        assert verify_reveal(r, signer.public_key_b64) is True

    def test_commitment_binds_preimage(self, signer):
        from platon.commit_reveal import verify_reveal

        b = self._beacon(signer)
        c = b.commit(np.zeros(64), 1, "2026-06-13T10:00:00Z")
        r = b.reveal(c["round"], "x", "2026-06-13T10:00:05Z")
        bad = dict(r)
        bad["preimage"] = r["preimage"] + "Z"  # guaranteed different
        assert verify_reveal(bad, signer.public_key_b64) is False
        bad2 = dict(r)
        bad2["random_hex"] = r["random_hex"] + "00"  # guaranteed different
        assert verify_reveal(bad2, signer.public_key_b64) is False

    def test_double_and_unknown_reveal_raise(self, signer):
        b = self._beacon(signer)
        c = b.commit(np.zeros(64), 1, "2026-06-13T10:00:00Z")
        b.reveal(c["round"], "x", "2026-06-13T10:00:05Z")
        with pytest.raises(ValueError):
            b.reveal(c["round"], "x", "2026-06-13T10:00:06Z")  # double
        with pytest.raises(ValueError):
            b.reveal(99999, "x", "2026-06-13T10:00:07Z")  # unknown


class TestSigning:
    def test_manifest_4field_self_verifies(self, signer):
        manifest = {
            "capabilities_count": 7,
            "generated_at": "2026-06-13T10:00:00Z",
            "protocol_version": "v2",
            "tools": [{"capability_id": "platon.random@v1"}],
        }
        manifest["signature"] = signer.sign_manifest(manifest)
        # canonical must include tools_hash (the live-hub 4-field form)
        assert "tools_hash:" in signer.manifest_canonical(manifest)
        assert signer.verify_manifest_signature(manifest) is True

    def test_manifest_tamper_rejected(self, signer):
        manifest = {
            "capabilities_count": 1,
            "generated_at": "2026-06-13T10:00:00Z",
            "protocol_version": "v2",
            "tools": [{"a": 1}],
        }
        manifest["signature"] = signer.sign_manifest(manifest)
        manifest["tools"] = [{"a": 2}]  # changes tools_hash
        assert signer.verify_manifest_signature(manifest) is False

    def test_receipt_7field_verifies(self, signer):
        receipt = signer.sign_receipt(
            {
                "nonce": "n1",
                "product_id": "prod-platon",
                "capability_id": "platon.random@v1",
                "price_usd": 0.004,
                "timestamp": "2026-06-13T10:00:00Z",
                "success": True,
                "latency_ms": 9,
            }
        )
        assert receipt["signature"]["algorithm"] == "ed25519"
        assert "public_key" not in receipt["signature"]  # hub receipt form
        assert signer.verify_receipt(receipt) is True
