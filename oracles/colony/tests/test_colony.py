import math

import numpy as np
import pytest
from httpx import ASGITransport, AsyncClient

from colony import tsp
from colony.main import app


def _square():
    # unit square; the optimal tour is the 4-cycle of length 4
    return [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]]


class TestTSP:
    def test_tour_is_valid_permutation(self):
        rng = np.random.default_rng(7)
        pts = rng.random((30, 2)).tolist()
        r = tsp.solve(pts, iterations=2000)
        assert sorted(r["tour"]) == list(range(30))
        assert len(set(r["tour"])) == 30
        assert r["n"] == 30

    def test_two_opt_no_worse_than_nearest_neighbour(self):
        rng = np.random.default_rng(11)
        pts = rng.random((40, 2)).tolist()
        r = tsp.solve(pts, iterations=5000)
        # 2-opt only ever accepts strictly-improving moves
        assert r["length"] <= r["nn_length"] + 1e-9

    def test_length_at_least_lower_bound(self):
        # admissibility must hold across many random instances
        for seed in range(15):
            rng = np.random.default_rng(seed)
            n = int(rng.integers(3, 50))
            pts = rng.random((n, 2)).tolist()
            r = tsp.solve(pts, iterations=3000)
            assert r["length"] >= r["lower_bound"] - 1e-9
            assert r["gap"] >= -1e-9

    def test_square_is_optimal_four_cycle(self):
        r = tsp.solve(_square(), iterations=1000)
        assert math.isclose(r["length"], 4.0, abs_tol=1e-9)
        # the optimal 4-cycle visits adjacent corners (no diagonal of length sqrt(2))
        D = tsp.distance_matrix(np.asarray(_square(), dtype=float))
        tour = r["tour"]
        for i in range(4):
            edge = D[tour[i], tour[(i + 1) % 4]]
            assert math.isclose(edge, 1.0, abs_tol=1e-9)

    def test_lower_bound_admissible_on_square(self):
        # each corner's cheapest edge is 1.0 -> bound = 4*1/2 = 2.0 <= optimum 4.0
        D = tsp.distance_matrix(np.asarray(_square(), dtype=float))
        assert math.isclose(tsp.lower_bound(D), 2.0, abs_tol=1e-9)

    def test_rejects_too_few_points(self):
        with pytest.raises(ValueError):
            tsp.solve([[0.0, 0.0], [1.0, 1.0]], iterations=10)

    def test_rejects_bad_shape(self):
        with pytest.raises(ValueError):
            tsp.solve([[0.0, 0.0, 0.0], [1.0, 1.0, 1.0], [2.0, 2.0, 2.0]], iterations=10)

    def test_two_opt_untangles_a_crossing(self):
        # a self-crossing order of the square; 2-opt must shorten it to 4.0
        pts = _square()
        D = tsp.distance_matrix(np.asarray(pts, dtype=float))
        crossing = [0, 2, 1, 3]  # crosses the diagonals -> length 4*sqrt(2)
        before = tsp.tour_length(crossing, D)
        after = tsp.tour_length(tsp.two_opt(crossing, D, 1000), D)
        assert after < before
        assert math.isclose(after, 4.0, abs_tol=1e-9)


class TestColonyApp:
    @pytest.mark.asyncio
    async def test_invoke_roundtrip(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://t") as c:
            resp = (
                await c.post(
                    "/ai-market/v2/invoke",
                    json={
                        "capability_id": "colony.optimize@v1",
                        "input": {"points": _square(), "iterations": 1000},
                    },
                )
            ).json()
        assert resp["ok"] is True
        out = resp["output"]
        assert sorted(out["tour"]) == [0, 1, 2, 3]
        assert math.isclose(out["length"], 4.0, abs_tol=1e-9)
        assert out["length"] >= out["lower_bound"] - 1e-9
        assert out["gap"] >= -1e-9
        # receipt + provenance envelope present
        assert "receipt" in resp and "provenance" in resp
        assert resp["provenance"]["source"] == "prod-colony"

    @pytest.mark.asyncio
    async def test_invoke_rejects_too_few_points(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://t") as c:
            resp = (
                await c.post(
                    "/ai-market/v2/invoke",
                    json={"capability_id": "colony.optimize@v1", "input": {"points": [[0, 0], [1, 1]]}},
                )
            ).json()
        assert resp["ok"] is False

    @pytest.mark.asyncio
    async def test_manifest_signed(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://t") as c:
            m = (await c.get("/ai-market/v2/manifest")).json()
        ids = {t["capability_id"] for t in m["tools"]}
        assert ids == {"colony.optimize@v1"}
        assert app.state.protocol.signer.verify_manifest_signature(m) is True

    @pytest.mark.asyncio
    async def test_health(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://t") as c:
            h = (await c.get("/api/health")).json()
        assert h["status"] == "ok"
        assert h["oracle"] == "prod-colony"
