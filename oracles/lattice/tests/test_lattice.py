import numpy as np
import pytest
from httpx import ASGITransport, AsyncClient

from lattice import halton
from lattice.main import app


def _max_gap(xs):
    """Largest gap between consecutive sorted 1D samples, including both ends [0,1]."""
    s = sorted(xs)
    edges = [0.0] + s + [1.0]
    return max(b - a for a, b in zip(edges, edges[1:]))


class TestHaltonMath:
    def test_radical_inverse_base2(self):
        # van der Corput in base 2: 1->.1=0.5, 2->.01=0.25, 3->.11=0.75
        assert halton.radical_inverse(1, 2) == pytest.approx(0.5)
        assert halton.radical_inverse(2, 2) == pytest.approx(0.25)
        assert halton.radical_inverse(3, 2) == pytest.approx(0.75)
        assert halton.radical_inverse(4, 2) == pytest.approx(0.125)

    def test_radical_inverse_base3(self):
        # base 3: 1->.1=1/3, 3->.01=1/9
        assert halton.radical_inverse(1, 3) == pytest.approx(1 / 3)
        assert halton.radical_inverse(3, 3) == pytest.approx(1 / 9)

    def test_deterministic(self):
        a = halton.halton(500, 3, skip=7)
        b = halton.halton(500, 3, skip=7)
        assert a == b
        # different args -> different points
        assert halton.halton(500, 3, skip=8) != a

    def test_points_in_unit_cube(self):
        pts = halton.halton(1000, 4)
        for p in pts:
            assert len(p) == 4
            for c in p:
                assert 0.0 <= c < 1.0

    def test_dim_and_bases(self):
        out = halton.run(10, dim=5)
        assert out["dim"] == 5
        assert out["count"] == 10
        assert out["bases"] == [2, 3, 5, 7, 11]
        assert all(len(p) == 5 for p in out["points"])

    def test_skip_offsets_sequence(self):
        full = halton.halton(10, 2, skip=0)
        skipped = halton.halton(7, 2, skip=3)
        # skipping 3 should reproduce the tail of the longer run
        assert skipped == full[3:]

    def test_bounds_validation(self):
        with pytest.raises(ValueError):
            halton.halton(0, 2)
        with pytest.raises(ValueError):
            halton.halton(halton.MAX_COUNT + 1, 2)
        with pytest.raises(ValueError):
            halton.halton(10, 0)
        with pytest.raises(ValueError):
            halton.halton(10, halton.MAX_DIM + 1)
        with pytest.raises(ValueError):
            halton.halton(10, 2, skip=-1)


class TestLowDiscrepancy:
    def test_1d_coverage_far_more_even_than_random(self):
        """The product claim: max gap of the quasi-random sequence is much
        smaller than white noise's, i.e. it fills [0,1) more evenly."""
        n = 512
        qmc = [p[0] for p in halton.halton(n, 1)]
        qmc_gap = _max_gap(qmc)

        # average random max-gap over several seeds (random is noisy)
        rng = np.random.default_rng(0)
        rand_gaps = [_max_gap(rng.random(n).tolist()) for _ in range(20)]
        rand_gap = float(np.mean(rand_gaps))

        # Halton base-2 max gap is ~2/n; random's is ~ln(n)/n — several x larger.
        assert qmc_gap < rand_gap / 3.0
        # and never worse than a couple of cells wide
        assert qmc_gap < 4.0 / n

    def test_2d_more_uniform_cell_occupancy(self):
        """In 2D, bin into a g x g grid: quasi-random spreads across many more
        distinct cells than white noise for the same point count."""
        n = 1024
        g = 32  # n == g*g -> ideal is one point per cell
        pts = np.array(halton.halton(n, 2))
        cells = set(map(tuple, np.floor(pts * g).astype(int)))

        rng = np.random.default_rng(1)
        rand_occ = []
        for _ in range(20):
            r = rng.random((n, 2))
            rand_occ.append(len(set(map(tuple, np.floor(r * g).astype(int)))))
        rand_cells = float(np.mean(rand_occ))

        # Halton hits far more cells; random leaves many empty (clumps).
        # Random occupies ~(1-1/e)*g*g ~= 0.63*g*g; Halton clears 0.75*g*g.
        assert len(cells) > rand_cells * 1.1
        assert len(cells) > 0.75 * g * g

    def test_qmc_integration_beats_random(self):
        """Quasi-Monte-Carlo estimate of a smooth integral converges with
        lower error than plain Monte-Carlo at the same sample budget."""
        n = 2048
        # integral of sum of coords over [0,1)^2 == 1.0
        pts = np.array(halton.halton(n, 2))
        qmc_err = abs(pts.sum(axis=1).mean() - 1.0)

        rng = np.random.default_rng(2)
        mc_errs = [abs(rng.random((n, 2)).sum(axis=1).mean() - 1.0) for _ in range(30)]
        mc_err = float(np.mean(mc_errs))

        assert qmc_err < mc_err


class TestLatticeApp:
    @pytest.mark.asyncio
    async def test_invoke_roundtrip(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://t") as c:
            resp = (
                await c.post(
                    "/ai-market/v2/invoke",
                    json={
                        "capability_id": "lattice.sequence@v1",
                        "input": {"count": 64, "dim": 3, "skip": 0},
                    },
                )
            ).json()
        assert resp["ok"] is True
        out = resp["output"]
        assert out["sequence"].startswith("halton")
        assert out["count"] == 64
        assert out["dim"] == 3
        assert out["bases"] == [2, 3, 5]
        assert len(out["points"]) == 64
        for p in out["points"]:
            assert len(p) == 3 and all(0.0 <= c < 1.0 for c in p)
        # signed receipt + provenance present
        assert "receipt" in resp and "provenance" in resp
        assert resp["provenance"]["input_hash"]

    @pytest.mark.asyncio
    async def test_invoke_deterministic_across_calls(self):
        transport = ASGITransport(app=app)
        body = {"capability_id": "lattice.sequence@v1", "input": {"count": 32, "dim": 2}}
        async with AsyncClient(transport=transport, base_url="http://t") as c:
            a = (await c.post("/ai-market/v2/invoke", json=body)).json()["output"]
            b = (await c.post("/ai-market/v2/invoke", json=body)).json()["output"]
        assert a["points"] == b["points"]

    @pytest.mark.asyncio
    async def test_manifest_signed(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://t") as c:
            m = (await c.get("/ai-market/v2/manifest")).json()
        ids = {t["capability_id"] for t in m["tools"]}
        assert ids == {"lattice.sequence@v1"}
        assert app.state.protocol.signer.verify_manifest_signature(m) is True
