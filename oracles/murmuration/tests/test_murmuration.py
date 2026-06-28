import math

import numpy as np
import pytest
from httpx import ASGITransport, AsyncClient

from murmuration import consensus
from murmuration.main import app


class TestEstimators:
    def test_median_known_input(self):
        assert consensus.median([3, 1, 2]) == 2.0
        # even count -> average of the two middle values
        assert consensus.median([1, 2, 3, 4]) == 2.5

    def test_trimmed_mean_drops_tails(self):
        # 10 values; trim=0.1 drops one from each end -> mean of 2..9
        data = list(range(1, 11))  # 1..10, mean = 5.5
        tm = consensus.trimmed_mean(data, trim=0.1)
        assert tm == pytest.approx(sum(range(2, 10)) / 8)  # mean of 2..9 = 5.5
        # plain mean when trim=0
        assert consensus.trimmed_mean(data, trim=0.0) == pytest.approx(5.5)

    def test_biweight_matches_mean_on_clean_gaussian(self):
        rng = np.random.default_rng(0)
        data = rng.normal(loc=10.0, scale=1.0, size=2000)
        bw = consensus.biweight_location(data)
        assert bw == pytest.approx(float(np.mean(data)), abs=0.1)

    def test_single_value(self):
        out = consensus.aggregate([42.0])
        assert out["n"] == 1
        assert out["median"] == 42.0
        assert out["biweight"] == 42.0
        assert out["converged_value"] == pytest.approx(42.0)
        assert out["iterations"] == 0

    def test_rejects_empty_and_nonfinite(self):
        with pytest.raises(ValueError):
            consensus.aggregate([])
        with pytest.raises(ValueError):
            consensus.aggregate([1.0, float("nan")])
        with pytest.raises(ValueError):
            consensus.aggregate([1.0, float("inf")])


class TestRobustness:
    def test_outlier_barely_moves_robust_estimators(self):
        # A tight cluster of honest submissions...
        clean = [10.0, 10.1, 9.9, 10.2, 9.8, 10.05, 9.95, 10.15, 9.85, 10.0]
        base_mean = float(np.mean(clean))
        base_tm = consensus.trimmed_mean(clean, 0.1)
        base_bw = consensus.biweight_location(clean)

        # ...plus one wildly adversarial submission.
        poisoned = clean + [10_000.0]
        new_mean = float(np.mean(poisoned))
        new_tm = consensus.trimmed_mean(poisoned, 0.1)
        new_bw = consensus.biweight_location(poisoned)

        # The raw mean is dragged hundreds of units away.
        assert abs(new_mean - base_mean) > 100.0
        # The robust estimators barely budge (< 0.5 units).
        assert abs(new_tm - base_tm) < 0.5
        assert abs(new_bw - base_bw) < 0.5
        # And they stay near the honest centre.
        assert abs(new_bw - base_mean) < 0.5

    def test_biweight_fully_rejects_extreme_outlier(self):
        # The biweight should be even closer to the honest centre than the
        # trimmed mean when the outlier is extreme (redescending -> zero weight).
        clean = [5.0] * 9
        poisoned = clean + [1e9]
        assert consensus.biweight_location(poisoned) == pytest.approx(5.0, abs=1e-6)


class TestDeGroot:
    def test_converges_to_arithmetic_mean(self):
        rng = np.random.default_rng(1)
        for _ in range(20):
            data = rng.normal(size=rng.integers(2, 50)).tolist()
            out = consensus.degroot_consensus(data)
            assert out["converged_value"] == pytest.approx(float(np.mean(data)), abs=1e-9)
            assert out["iterations"] >= 1

    def test_complete_graph_converges_in_one_step(self):
        # W x for the complete graph is the mean broadcast; one update flattens
        # the spread to zero, so convergence is reached after a single iteration.
        out = consensus.degroot_consensus([0.0, 1.0, 2.0, 3.0, 100.0])
        assert out["iterations"] == 1
        assert out["converged_value"] == pytest.approx(21.2)  # mean of the five

    def test_already_converged(self):
        out = consensus.degroot_consensus([7.0, 7.0, 7.0])
        assert out["iterations"] == 0
        assert out["converged_value"] == pytest.approx(7.0)


class TestMurmurationApp:
    @pytest.mark.asyncio
    async def test_invoke_roundtrip(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://t") as c:
            resp = await c.post(
                "/ai-market/v2/invoke",
                json={
                    "capability_id": "murmuration.aggregate@v1",
                    "input": {"values": [1, 2, 3, 4, 100], "trim": 0.2},
                },
            )
            env = resp.json()
        assert env["ok"] is True
        out = env["output"]
        assert out["n"] == 5
        assert out["median"] == 3.0
        # converged value == arithmetic mean (1+2+3+4+100)/5 = 22
        assert out["converged_value"] == pytest.approx(22.0)
        # trimmed mean with trim=0.2 drops the 100 and the 1 -> mean of 2,3,4 = 3
        assert out["trimmed_mean"] == pytest.approx(3.0)
        # receipt + provenance present and well-formed
        assert env["price_usd"] == pytest.approx(0.002)
        assert "receipt" in env and "signature" in env["receipt"]
        assert "provenance" in env and "input_hash" in env["provenance"]

    @pytest.mark.asyncio
    async def test_unknown_capability(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://t") as c:
            resp = await c.post(
                "/ai-market/v2/invoke",
                json={"capability_id": "murmuration.nope@v1", "input": {"values": [1]}},
            )
        body = resp.json()
        assert body["ok"] is False

    @pytest.mark.asyncio
    async def test_manifest_signed(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://t") as c:
            m = (await c.get("/ai-market/v2/manifest")).json()
        ids = {t["capability_id"] for t in m["tools"]}
        assert ids == {"murmuration.aggregate@v1"}
        assert app.state.protocol.signer.verify_manifest_signature(m) is True

    @pytest.mark.asyncio
    async def test_receipt_verifies(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://t") as c:
            env = (
                await c.post(
                    "/ai-market/v2/invoke",
                    json={
                        "capability_id": "murmuration.aggregate@v1",
                        "input": {"values": [10.0, 11.0, 9.0]},
                    },
                )
            ).json()
        assert app.state.protocol.signer.verify_receipt(env["receipt"]) is True

    @pytest.mark.asyncio
    async def test_health(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://t") as c:
            h = (await c.get("/api/health")).json()
        assert h["status"] == "ok"
        assert h["capabilities"] == 1
