

# ── Degenerate group elements ────────────────────────────────────
# `verify` is a public capability that takes g from the caller, and it accepted any g in
# [0, N). For g in {0, 1, N-1} the equation π^l·g^r ≡ y is an identity, so a proof claiming
# a million sequential squarings verified with no work at all — confirmed against
# production before the fix.

import pytest

from chronos import vdf


@pytest.mark.parametrize("g", [0, 1, vdf.RSA_2048 - 1])
def test_a_degenerate_generator_cannot_forge_elapsed_time(g):
    N = vdf.RSA_2048
    T = 1_000_000
    y = g if g < 2 else pow(g, 1 << 4, N)   # for these g, y does not depend on T
    l = vdf.hash_to_prime(g, y, T)          # Fiat-Shamir is public, the caller can compute it
    assert not vdf.verify(g, y, T, 0 if g == 0 else 1, l), (
        f"g={g} verified a proof of {T:,} squarings that cost nothing"
    )


def test_hash_to_group_lands_in_the_safe_range():
    N = vdf.RSA_2048
    for seed in ("a", "b", "", "x" * 500):
        g = vdf.hash_to_group(seed)
        assert 2 <= g <= N - 2, seed


def test_hash_to_group_draws_more_bits_than_the_modulus():
    """Reducing exactly 2048 bits mod a 2048-bit N leaves ~28% of residues twice as likely;
    the extra 128 bits put the bias under 2^-128."""
    import inspect
    src = inspect.getsource(vdf.hash_to_group)
    assert "+ 128" in src, "the bias margin was removed"
