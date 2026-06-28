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
