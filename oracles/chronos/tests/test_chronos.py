import pytest
from httpx import ASGITransport, AsyncClient

from chronos import vdf
from chronos.main import app


class TestVDF:
    def test_eval_verify_roundtrip(self):
        g = vdf.hash_to_group("hello")
        T = 1000
        y = vdf.evaluate(g, T)
        p = vdf.prove(g, y, T)
        assert vdf.verify(g, y, T, p["pi"], p["l"]) is True

    def test_deterministic(self):
        a = vdf.evaluate(vdf.hash_to_group("seed-1"), 500)
        b = vdf.evaluate(vdf.hash_to_group("seed-1"), 500)
        assert a == b
        assert vdf.evaluate(vdf.hash_to_group("seed-2"), 500) != a

    def test_wrong_output_rejected(self):
        g = vdf.hash_to_group("x")
        T = 800
        y = vdf.evaluate(g, T)
        p = vdf.prove(g, y, T)
        assert vdf.verify(g, (y + 1) % vdf.RSA_2048, T, p["pi"], p["l"]) is False

    def test_forged_proof_rejected(self):
        g = vdf.hash_to_group("y")
        T = 800
        y = vdf.evaluate(g, T)
        p = vdf.prove(g, y, T)
        assert vdf.verify(g, y, T, (p["pi"] + 1) % vdf.RSA_2048, p["l"]) is False

    def test_wrong_difficulty_rejected(self):
        g = vdf.hash_to_group("z")
        T = 800
        y = vdf.evaluate(g, T)
        p = vdf.prove(g, y, T)
        # claiming a different T must fail (l is bound to T via Fiat-Shamir)
        assert vdf.verify(g, y, T + 1, p["pi"], p["l"]) is False

    def test_l_is_prime(self):
        g = vdf.hash_to_group("p")
        y = vdf.evaluate(g, 300)
        l = vdf.prove(g, y, 300)["l"]
        assert vdf._is_probable_prime(l) and l.bit_length() <= 128


class TestChronosApp:
    @pytest.mark.asyncio
    async def test_eval_then_verify_via_invoke(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://t") as c:
            ev = (await c.post("/ai-market/v2/invoke", json={"capability_id": "chronos.eval@v1", "input": {"seed": "agent-1", "difficulty": 1500}})).json()
            assert ev["ok"] is True
            out = ev["output"]
            assert out["scheme"].startswith("wesolowski-vdf")
            vr = (await c.post("/ai-market/v2/invoke", json={"capability_id": "chronos.verify@v1", "input": out})).json()
            assert vr["ok"] is True and vr["output"]["valid"] is True

    @pytest.mark.asyncio
    async def test_manifest_signed(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://t") as c:
            m = (await c.get("/ai-market/v2/manifest")).json()
        ids = {t["capability_id"] for t in m["tools"]}
        assert ids == {"chronos.eval@v1", "chronos.verify@v1"}
        assert app.state.protocol.signer.verify_manifest_signature(m) is True


class TestVDFHardening:
    """Adversarial / malformed-input rejection — guards against verification false positives
    and resource abuse (backs the 'implementation risks' review points)."""

    def _valid(self):
        g = vdf.hash_to_group("harden")
        T = 800
        y = vdf.evaluate(g, T)
        p = vdf.prove(g, y, T)
        return g, y, T, p["pi"], p["l"]

    def test_out_of_range_group_elements_rejected(self):
        g, y, T, pi, l = self._valid()
        assert vdf.verify(g, y + vdf.RSA_2048, T, pi, l) is False       # y >= N
        assert vdf.verify(g, y, T, pi + vdf.RSA_2048, l) is False       # pi >= N
        assert vdf.verify(g, -1, T, pi, l) is False                      # y < 0

    def test_difficulty_out_of_bounds_rejected(self):
        g, y, T, pi, l = self._valid()
        assert vdf.verify(g, y, 0, pi, l) is False                       # T < 1
        assert vdf.verify(g, y, vdf.MAX_DIFFICULTY + 1, pi, l) is False  # T > cap

    def test_wrong_but_prime_challenge_rejected(self):
        g, y, T, pi, l = self._valid()
        other = vdf.hash_to_prime(g, y, T + 7)                           # a real prime, wrong transcript
        assert other != l
        assert vdf.verify(g, y, T, pi, other) is False

    def test_non_prime_or_degenerate_l_rejected(self):
        g, y, T, pi, l = self._valid()
        for bad in (0, 1, 2, l * l):                                     # composite / degenerate
            assert vdf.verify(g, y, T, pi, bad) is False

    def test_malformed_types_rejected(self):
        g, y, T, pi, l = self._valid()
        assert vdf.verify(g, y, T, pi, "not-an-int") is False
        assert vdf.verify(g, None, T, pi, l) is False

    def test_difficulty_is_clamped_in_run(self):
        out = vdf.run("seed", vdf.MAX_DIFFICULTY + 10_000)
        assert out["difficulty"] <= vdf.MAX_DIFFICULTY                   # DoS bound enforced
        out2 = vdf.run("seed", 0)
        assert out2["difficulty"] >= 1


def test_modulus_is_canonical_rsa2048():
    """Pin N to the canonical RSA-2048 challenge (617 digits, 2048 bits) so a corrupted
    constant — which would void the unknown-factorization assumption — can't regress."""
    import hashlib
    from chronos import vdf
    assert vdf.RSA_2048.bit_length() == 2048
    assert len(str(vdf.RSA_2048)) == 617
    assert hashlib.sha256(str(vdf.RSA_2048).encode()).hexdigest() == \
        "b3c2468add10e2a0c4a251d9d2bac4ba04d4b3527156ceead43a1305e03f1fc0"
