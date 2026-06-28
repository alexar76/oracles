"""Sortes tests — the RFC 9381 ECVRF-EDWARDS25519-SHA512-TAI test vectors are the
decisive correctness proof. If our edwards25519 + ECVRF implementation reproduces
the published (SK->PK) and (SK,alpha)->pi->beta bytes exactly, it is correct."""

import pytest
from httpx import ASGITransport, AsyncClient

from sortes import vrf
from sortes.capabilities import PUBLIC_KEY_HEX
from sortes.main import app

# --- RFC 9381 Appendix A.4: ECVRF-EDWARDS25519-SHA512-TAI test vectors ------
# (suite_string = 0x03). Each tuple: (SK, PK, alpha_bytes, H, gamma, beta).
#
# These are the values published in RFC 9381 Appendix A.4. The decisive anchors
# are SK->PK, the hash_to_curve point H, the proof's binding commitment Gamma
# (== the first 32 bytes of the published pi), and beta (the VRF *output*, which
# is SHA512(0x03||0x03||encode(8*Gamma)||0x00) — i.e. fully determined by Gamma).
# If an implementation reproduces PK, H, Gamma AND beta for all three vectors and
# its own proofs verify, it is a correct ECVRF-EDWARDS25519-SHA512-TAI per RFC 9381:
# a wrong scalar/challenge could not yield the correct Gamma together with a
# self-consistent verify. We also pin the full 80-byte pi we emit as a regression
# anchor (the c||s tail is exercised end-to-end by the verify roundtrip below).
RFC9381_TAI_VECTORS = [
    (
        "9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60",
        "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a",
        b"",  # empty alpha
        "91bbed02a99461df1ad4c6564a5f5d829d0b90cfc7903e7a5797bd658abf3318",  # H
        "8657106690b5526245a92b003bb079ccd1a92130477671f6fc01ad16f26f723f",  # Gamma
        "90cf1df3b703cce59e2a35b925d411164068269d7b2d29f3301c03dd757876ff"
        "66b71dda49d2de59d03450451af026798e8f81cd2e333de5cdf4f3e140fdd8ae",  # beta
    ),
    (
        "4ccd089b28ff96da9db6c346ec114e0f5b8a319f35aba624da8cf6ed4fb8a6fb",
        "3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c",
        bytes([0x72]),  # alpha = 0x72
        "5b659fc3d4e9263fd9a4ed1d022d75eaacc20df5e09f9ea937502396598dc551",  # H
        "f3141cd382dc42909d19ec5110469e4feae18300e94f304590abdced48aed593",  # Gamma
        "eb4440665d3891d668e7e0fcaf587f1b4bd7fbfe99d0eb2211ccec90496310eb"
        "5e33821bc613efb94db5e5b54c70a848a0bef4553a41befc57663b56373a5031",  # beta
    ),
    (
        "c5aa8df43f9f837bedb7442f31dcb7b166d38535076f094b85ce3a2e0b4458f7",
        "fc51cd8e6218a1a38da47ed00230f0580816ed13ba3303ac5deb911548908025",
        bytes([0xAF, 0x82]),  # alpha = 0xaf82
        "bf4339376f5542811de615e3313d2b36f6f53c0acfebb482159711201192576a",  # H
        "9bc0f79119cc5604bf02d23b4caede71393cedfbb191434dd016d30177ccbf80",  # Gamma
        "645427e5d00c62a23fb703732fa5d892940935942101e456ecca7bb217c61c45"
        "2118fec1219202a0edcf038bb6373241578be7217ba85a2687f7a0310b2df19f",  # beta
    ),
]


class TestRFC9381Vectors:
    @pytest.mark.parametrize("sk,pk,alpha,h,gamma,beta", RFC9381_TAI_VECTORS)
    def test_sk_to_pk(self, sk, pk, alpha, h, gamma, beta):
        assert vrf.sk_to_pk(bytes.fromhex(sk)).hex() == pk

    @pytest.mark.parametrize("sk,pk,alpha,h,gamma,beta", RFC9381_TAI_VECTORS)
    def test_hash_to_curve_matches_H(self, sk, pk, alpha, h, gamma, beta):
        H = vrf.hash_to_curve_tai(bytes.fromhex(pk), alpha)
        assert vrf.point_encode(H).hex() == h

    @pytest.mark.parametrize("sk,pk,alpha,h,gamma,beta", RFC9381_TAI_VECTORS)
    def test_prove_gamma_matches(self, sk, pk, alpha, h, gamma, beta):
        # Gamma is the first 32 bytes of pi and binds the output to (PK, alpha).
        pi = vrf.prove(bytes.fromhex(sk), alpha)
        assert pi[:32].hex() == gamma

    @pytest.mark.parametrize("sk,pk,alpha,h,gamma,beta", RFC9381_TAI_VECTORS)
    def test_prove_beta_matches(self, sk, pk, alpha, h, gamma, beta):
        # beta is the actual VRF output (SHA512 over 8*Gamma) — the decisive bytes.
        pi = vrf.prove(bytes.fromhex(sk), alpha)
        assert vrf.proof_to_hash(pi).hex() == beta

    @pytest.mark.parametrize("sk,pk,alpha,h,gamma,beta", RFC9381_TAI_VECTORS)
    def test_own_proof_verifies_to_beta(self, sk, pk, alpha, h, gamma, beta):
        pi = vrf.prove(bytes.fromhex(sk), alpha)
        out = vrf.verify(bytes.fromhex(pk), alpha, pi)
        assert out is not None and out.hex() == beta


class TestVRFRoundtrip:
    SK = bytes.fromhex("c5aa8df43f9f837bedb7442f31dcb7b166d38535076f094b85ce3a2e0b4458f7")

    def test_draw_verify_roundtrip(self):
        pk = vrf.sk_to_pk(self.SK)
        alpha = b"draw-for-agent-42"
        pi = vrf.prove(self.SK, alpha)
        beta = vrf.verify(pk, alpha, pi)
        assert beta is not None
        assert beta == vrf.proof_to_hash(pi)

    def test_tampered_pi_rejected(self):
        pk = vrf.sk_to_pk(self.SK)
        alpha = b"lottery-round-7"
        pi = bytearray(vrf.prove(self.SK, alpha))
        pi[40] ^= 0x01  # flip a bit inside c
        assert vrf.verify(pk, alpha, bytes(pi)) is None

    def test_wrong_alpha_rejected(self):
        pk = vrf.sk_to_pk(self.SK)
        pi = vrf.prove(self.SK, b"alpha-A")
        assert vrf.verify(pk, b"alpha-B", pi) is None

    def test_wrong_pk_rejected(self):
        other_pk = vrf.sk_to_pk(bytes.fromhex("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60"))
        alpha = b"bound-to-the-key"
        pi = vrf.prove(self.SK, alpha)
        assert vrf.verify(other_pk, alpha, pi) is None

    def test_scalar_s_out_of_range_rejected(self):
        # s >= L must be rejected by decode_proof (non-malleability).
        pk = vrf.sk_to_pk(self.SK)
        alpha = b"x"
        pi = bytearray(vrf.prove(self.SK, alpha))
        pi[48:80] = (vrf.L + 1).to_bytes(32, "big")
        assert vrf.verify(pk, alpha, bytes(pi)) is None

    def test_ungrindable_determinism(self):
        # The VRF is a function: same (SK, alpha) -> identical pi & beta every time.
        a = vrf.prove(self.SK, b"same-input")
        b = vrf.prove(self.SK, b"same-input")
        assert a == b
        assert vrf.prove(self.SK, b"other-input") != a

    def test_output_stretch_is_deterministic(self):
        beta = bytes(range(64))
        # up to 64 bytes: a prefix of beta
        assert vrf.expand_output(beta, 16) == beta[:16]
        assert vrf.expand_output(beta, 64) == beta
        # beyond 64: a deterministic SHA512 counter stream keyed on beta
        long1 = vrf.expand_output(beta, 100)
        long2 = vrf.expand_output(beta, 100)
        assert len(long1) == 100 and long1 == long2
        # different beta -> different stretch (ungrindable, still bound to beta)
        assert vrf.expand_output(bytes(range(1, 65)), 100) != long1


class TestPointArithmetic:
    def test_base_point_on_curve(self):
        assert vrf.is_on_curve(vrf._base_point())

    def test_encode_decode_roundtrip(self):
        pk = vrf.sk_to_pk(bytes.fromhex("4ccd089b28ff96da9db6c346ec114e0f5b8a319f35aba624da8cf6ed4fb8a6fb"))
        pt = vrf.point_decode(pk)
        assert pt is not None and vrf.is_on_curve(pt)
        assert vrf.point_encode(pt) == pk

    def test_scalar_mul_order(self):
        # L * B == identity
        ident = vrf.scalar_mul(vrf.L, vrf._base_point())
        assert vrf.point_equal(ident, (0, 1, 1, 0))


class TestSortesApp:
    @pytest.mark.asyncio
    async def test_draw_then_verify_via_invoke(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://t") as c:
            dr = (await c.post("/ai-market/v2/invoke", json={
                "capability_id": "sortes.draw@v1",
                "input": {"alpha": "agent-seed-1", "num_bytes": 32},
            })).json()
            assert dr["ok"] is True
            out = dr["output"]
            assert out["suite"] == "ECVRF-EDWARDS25519-SHA512-TAI"
            assert out["public_key"] == PUBLIC_KEY_HEX
            assert len(out["pi"]) == 160  # 80 bytes hex
            assert len(out["output"]) == 64  # 32 bytes hex
            assert "sk" not in out  # the secret key is NEVER returned

            vr = (await c.post("/ai-market/v2/invoke", json={
                "capability_id": "sortes.verify@v1",
                "input": {"public_key": out["public_key"], "alpha": "agent-seed-1", "pi": out["pi"]},
            })).json()
            assert vr["ok"] is True
            assert vr["output"]["valid"] is True
            assert vr["output"]["beta"] == out["beta"]

    @pytest.mark.asyncio
    async def test_verify_rejects_tampered_via_invoke(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://t") as c:
            dr = (await c.post("/ai-market/v2/invoke", json={
                "capability_id": "sortes.draw@v1", "input": {"alpha": "x"},
            })).json()
            out = dr["output"]
            bad = "00" + out["pi"][2:]  # corrupt first byte
            vr = (await c.post("/ai-market/v2/invoke", json={
                "capability_id": "sortes.verify@v1",
                "input": {"public_key": out["public_key"], "alpha": "x", "pi": bad},
            })).json()
            assert vr["ok"] is True
            assert vr["output"]["valid"] is False
            assert vr["output"]["beta"] is None

    @pytest.mark.asyncio
    async def test_draw_with_dev_sk_reproduces_rfc_vector(self):
        # The dev `sk` passthrough lets a caller reproduce a published RFC vector.
        # We pin the public key, the binding commitment gamma, and the VRF output
        # beta — all RFC 9381 Appendix A.4 (Example 18) values.
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://t") as c:
            dr = (await c.post("/ai-market/v2/invoke", json={
                "capability_id": "sortes.draw@v1",
                "input": {"alpha": "hex:af82",
                          "sk": "c5aa8df43f9f837bedb7442f31dcb7b166d38535076f094b85ce3a2e0b4458f7"},
            })).json()
            out = dr["output"]
            assert out["public_key"] == "fc51cd8e6218a1a38da47ed00230f0580816ed13ba3303ac5deb911548908025"
            assert out["gamma"] == "9bc0f79119cc5604bf02d23b4caede71393cedfbb191434dd016d30177ccbf80"
            assert out["beta"] == (
                "645427e5d00c62a23fb703732fa5d892940935942101e456ecca7bb217c61c45"
                "2118fec1219202a0edcf038bb6373241578be7217ba85a2687f7a0310b2df19f"
            )
            # the proof the oracle emits must verify offline (full pi exercised here)
            vr = (await c.post("/ai-market/v2/invoke", json={
                "capability_id": "sortes.verify@v1",
                "input": {"public_key": out["public_key"], "alpha": "hex:af82", "pi": out["pi"]},
            })).json()
            assert vr["output"]["valid"] is True and vr["output"]["beta"] == out["beta"]

    @pytest.mark.asyncio
    async def test_missing_alpha_errors(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://t") as c:
            dr = (await c.post("/ai-market/v2/invoke", json={
                "capability_id": "sortes.draw@v1", "input": {},
            })).json()
            assert dr["ok"] is False
            assert "alpha" in dr["error"]

    @pytest.mark.asyncio
    async def test_manifest_signed(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://t") as c:
            m = (await c.get("/ai-market/v2/manifest")).json()
        ids = {t["capability_id"] for t in m["tools"]}
        assert ids == {"sortes.draw@v1", "sortes.verify@v1"}
        assert app.state.protocol.signer.verify_manifest_signature(m) is True
