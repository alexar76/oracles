

# ── draw → verify must round-trip ────────────────────────────────
# `draw` emitted `alpha` as a bare hex string; `_alpha_to_bytes` only decodes hex behind a
# `hex:` prefix, so verify UTF-8 encoded those hex characters and hashed 18 bytes where the
# prover had hashed 9. Every honest proof the oracle issued verified as false — a paid
# verification capability that could not confirm its own output.

from sortes import capabilities as C


def test_draw_output_verifies_as_issued():
    d = C._draw({"alpha": "test-seed"})
    out = C._verify({"public_key": d["public_key"], "alpha": d["alpha"], "pi": d["pi"]})
    assert out["valid"] is True, "the oracle cannot verify a proof it just produced"
    assert out["beta"] == d["beta"]


def test_the_original_seed_also_verifies():
    """A caller who kept their own seed string, rather than the echoed alpha, must not be
    told their valid proof is invalid either."""
    d = C._draw({"alpha": "test-seed"})
    assert C._verify({"public_key": d["public_key"], "alpha": "test-seed", "pi": d["pi"]})["valid"]


def test_a_hex_looking_seed_stays_text():
    """Decoding by shape would make the wire format ambiguous: 'deadbeef' as a seed means
    eight characters, and the proof binds to exact bytes."""
    assert C._alpha_to_bytes("deadbeef") == b"deadbeef"
    assert C._alpha_to_bytes("hex:deadbeef") == bytes.fromhex("deadbeef")


def test_forgeries_still_fail():
    d = C._draw({"alpha": "test-seed"})
    pk, pi = d["public_key"], d["pi"]
    assert not C._verify({"public_key": pk, "alpha": "hex:00", "pi": pi})["valid"]
    assert not C._verify({"public_key": pk, "alpha": d["alpha"], "pi": "00" * 40})["valid"]
    assert not C._verify({"public_key": "00" * 32, "alpha": d["alpha"], "pi": pi})["valid"]
