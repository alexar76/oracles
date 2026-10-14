"""ECVRF_validate_key (RFC 9381 §5.4.5): a public key of small order is not a key.

Before 2026-10-12 `verify` skipped this step. For the identity point (encoding 01 00..00) anyone
could build an accepted proof for ANY alpha without a secret key, and every such proof hashed to
the same beta — so Sortes's `verify`, which takes the key from its caller, would vouch for a fixed
output as a VRF draw. These tests build that forgery for every small-order point and require it to
be refused, while honest keys keep verifying.
"""

from __future__ import annotations

import secrets

import pytest
from httpx import ASGITransport, AsyncClient

from sortes import vrf
from sortes.capabilities import PUBLIC_KEY_HEX
from sortes.main import app

IDENTITY_ENCODING = bytes.fromhex("01" + "00" * 31)


def _small_order_points() -> set[bytes]:
    """All eight points of order dividing 8, found as L*P for random curve points P."""
    found: set[bytes] = set()
    for _ in range(4000):
        p = vrf.point_decode(secrets.token_bytes(32))
        if p is None:
            continue
        found.add(vrf.point_encode(vrf.scalar_mul(vrf.L, p)))
        if len(found) == 8:
            break
    return found


SMALL_ORDER = sorted(_small_order_points())


def _forge(pk: bytes, alpha: bytes) -> bytes:
    """A proof for `pk` with no secret key: Gamma = O, U = kB, V = kH, s = k."""
    y = vrf.point_decode(pk)
    h = vrf.hash_to_curve_tai(pk, alpha)
    k = secrets.randbelow(vrf.L)
    u = vrf.scalar_mul(k, vrf._base_point())
    v = vrf.scalar_mul(k, h)
    c = vrf._challenge_generation([y, h, vrf.IDENTITY, u, v])
    return vrf.point_encode(vrf.IDENTITY) + vrf.int_to_string(c, vrf.C_LEN) + vrf.int_to_string(k, vrf.Q_LEN)


def test_all_eight_small_order_points_are_found():
    assert len(SMALL_ORDER) == 8
    assert IDENTITY_ENCODING in SMALL_ORDER
    for enc in SMALL_ORDER:
        assert vrf.point_equal(vrf.scalar_mul(8, vrf.point_decode(enc)), vrf.IDENTITY)


@pytest.mark.parametrize("pk", SMALL_ORDER, ids=lambda b: b.hex()[:8])
def test_a_small_order_key_is_refused_with_a_forged_proof(pk):
    assert vrf.validate_key(vrf.point_decode(pk)) is False
    for alpha in (b"draw-1", b"draw-2"):
        assert vrf.verify(pk, alpha, _forge(pk, alpha)) is None


def test_the_forgery_is_exactly_what_validate_key_stops():
    """Without the key check the identity forgery verifies, for every alpha, to ONE beta."""
    pk = IDENTITY_ENCODING
    o = vrf.point_decode(pk)
    betas = set()
    for alpha in (b"a", b"b", b"c"):
        pi = _forge(pk, alpha)
        gamma, c, s = vrf.decode_proof(pi)
        h = vrf.hash_to_curve_tai(pk, alpha)
        u = vrf.point_add(vrf.scalar_mul(s, vrf._base_point()), vrf._negate(vrf.scalar_mul(c, o)))
        v = vrf.point_add(vrf.scalar_mul(s, h), vrf._negate(vrf.scalar_mul(c, gamma)))
        assert vrf._challenge_generation([o, h, gamma, u, v]) == c      # the rest of §5.3 accepts it
        betas.add(vrf.proof_to_hash(pi))
    assert len(betas) == 1


def test_honest_keys_still_verify():
    sk = secrets.token_bytes(32)
    pk = vrf.sk_to_pk(sk)
    assert vrf.validate_key(vrf.point_decode(pk)) is True
    pi = vrf.prove(sk, b"alpha")
    assert vrf.verify(pk, b"alpha", pi) == vrf.proof_to_hash(pi)


def test_non_canonical_and_sign_on_zero_encodings_are_refused():
    p_bytes = bytearray(vrf.P.to_bytes(32, "little"))                 # y = p (non-canonical)
    assert vrf.point_decode(bytes(p_bytes)) is None
    neg_zero = bytearray(IDENTITY_ENCODING)
    neg_zero[31] |= 0x80                                                 # x = 0 with the sign bit set
    assert vrf.point_decode(bytes(neg_zero)) is None


@pytest.mark.asyncio
async def test_the_verify_capability_refuses_the_forgery_and_names_the_key():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        forged = (await c.post("/ai-market/v2/invoke", json={
            "capability_id": "sortes.verify@v1",
            "input": {"public_key": IDENTITY_ENCODING.hex(), "alpha": "lottery-round-7",
                      "pi": _forge(IDENTITY_ENCODING, b"lottery-round-7").hex()},
        })).json()["output"]
        assert forged["valid"] is False and forged["issued_by_this_oracle"] is False
        draw = (await c.post("/ai-market/v2/invoke", json={
            "capability_id": "sortes.draw@v1", "input": {"alpha": "own"},
        })).json()["output"]
        own = (await c.post("/ai-market/v2/invoke", json={
            "capability_id": "sortes.verify@v1",
            "input": {"public_key": PUBLIC_KEY_HEX, "alpha": "own", "pi": draw["pi"]},
        })).json()["output"]
        assert own["valid"] is True and own["issued_by_this_oracle"] is True
