import math

import numpy as np
import pytest
from httpx import ASGITransport, AsyncClient

from turing import bluenoise
from turing.main import app


def _min_dist(points) -> float:
    arr = np.asarray(points, dtype=float)
    return bluenoise.min_pairwise_distance(arr)


class TestBlueNoise:
    def test_count_correct(self):
        for n in (1, 2, 17, 256):
            r = bluenoise.bluenoise(n, seed=7)
            assert r["count"] == n
            assert len(r["points"]) == n

    def test_points_in_unit_square(self):
        r = bluenoise.bluenoise(512, seed=3)
        arr = np.asarray(r["points"])
        assert arr.shape == (512, 2)
        assert arr.min() >= 0.0
        assert arr.max() < 1.0  # [0, 1)

    def test_blue_noise_property_beats_uniform(self):
        # The defining property: blue-noise min pairwise distance is MUCH larger
        # than that of the same number of uniform i.i.d. random points.
        n = 400
        bn = bluenoise.bluenoise(n, candidates=15, seed=42)
        bn_min = bn["min_distance"]

        rng = np.random.default_rng(42)
        # Average over several uniform draws so the comparison is robust.
        uniform_mins = []
        for _ in range(8):
            uni = rng.random((n, 2))
            uniform_mins.append(_min_dist(uni))
        uni_min_mean = float(np.mean(uniform_mins))

        # Blue-noise should be dramatically more spread out: require >= 5x.
        assert bn_min > 5.0 * uni_min_mean, (bn_min, uni_min_mean)

    def test_more_candidates_spreads_better(self):
        # More candidates -> greedier max-min -> larger (or equal) min distance.
        low = bluenoise.bluenoise(300, candidates=2, seed=11)["min_distance"]
        high = bluenoise.bluenoise(300, candidates=40, seed=11)["min_distance"]
        assert high > low

    def test_min_distance_matches_recompute(self):
        r = bluenoise.bluenoise(200, seed=9)
        assert math.isclose(r["min_distance"], _min_dist(r["points"]), rel_tol=1e-12)

    def test_deterministic_with_seed(self):
        a = bluenoise.bluenoise(150, candidates=12, seed=2024)
        b = bluenoise.bluenoise(150, candidates=12, seed=2024)
        assert a["points"] == b["points"]
        assert a["min_distance"] == b["min_distance"]
        assert a["seed"] == b["seed"] == 2024
        assert a["seed_source"] == "provided"

    def test_different_seed_different_set(self):
        a = bluenoise.bluenoise(150, seed=1)
        b = bluenoise.bluenoise(150, seed=2)
        assert a["points"] != b["points"]

    def test_no_seed_reports_os_entropy(self):
        r = bluenoise.bluenoise(20)
        assert r["seed_source"] == "os.urandom"
        assert isinstance(r["seed"], int)
        # Reported seed reproduces the exact set.
        again = bluenoise.bluenoise(20, seed=r["seed"])
        assert again["points"] == r["points"]

    def test_input_validation(self):
        with pytest.raises(ValueError):
            bluenoise.bluenoise(0)
        with pytest.raises(ValueError):
            bluenoise.bluenoise(bluenoise.MAX_COUNT + 1)
        with pytest.raises(ValueError):
            bluenoise.bluenoise(10, candidates=0)


class TestTuringApp:
    @pytest.mark.asyncio
    async def test_invoke_roundtrip(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://t") as c:
            resp = (
                await c.post(
                    "/ai-market/v2/invoke",
                    json={"capability_id": "turing.bluenoise@v1", "input": {"count": 128, "candidates": 12, "seed": 5}},
                )
            ).json()
        assert resp["ok"] is True
        out = resp["output"]
        assert out["count"] == 128
        assert len(out["points"]) == 128
        assert out["min_distance"] > 0.0
        # Receipt + provenance envelope present.
        assert "receipt" in resp and "provenance" in resp
        assert resp["provenance"]["source"] == "prod-turing"

    @pytest.mark.asyncio
    async def test_invoke_deterministic_via_api(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://t") as c:
            body = {"capability_id": "turing.bluenoise@v1", "input": {"count": 64, "seed": 99}}
            a = (await c.post("/ai-market/v2/invoke", json=body)).json()["output"]
            b = (await c.post("/ai-market/v2/invoke", json=body)).json()["output"]
        assert a["points"] == b["points"]

    @pytest.mark.asyncio
    async def test_manifest_signed(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://t") as c:
            m = (await c.get("/ai-market/v2/manifest")).json()
        ids = {t["capability_id"] for t in m["tools"]}
        assert ids == {"turing.bluenoise@v1"}
        assert app.state.protocol.signer.verify_manifest_signature(m) is True

    @pytest.mark.asyncio
    async def test_health(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://t") as c:
            h = (await c.get("/api/health")).json()
        assert h["status"] == "ok"
        assert h["oracle"] == "prod-turing"
