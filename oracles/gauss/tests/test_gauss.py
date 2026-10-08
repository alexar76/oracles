import math

import numpy as np
import pytest
from httpx import ASGITransport, AsyncClient

from gauss import gp
from gauss.main import app


# A tiny, well-conditioned 1D example: y = sin(x) sampled at a handful of points.
TRAIN_X = [[0.0], [1.0], [2.0], [3.0], [4.0], [5.0]]
TRAIN_Y = [math.sin(x[0]) for x in TRAIN_X]
HP = {"length_scale": 1.0, "signal_var": 1.0, "noise_var": 1e-6}


class TestGPMath:
    def test_interpolates_through_training_points(self):
        # At a training x, the posterior mean ~ y (noiseless limit) and var ~ sigma_n^2.
        out = gp.field({"X": TRAIN_X, "y": TRAIN_Y, "query": TRAIN_X, "hyperparams": HP})
        for i, yi in enumerate(TRAIN_Y):
            assert out["mean"][i] == pytest.approx(yi, abs=1e-3)
            # variance collapses to ~ the noise floor at an observation
            assert out["var"][i] == pytest.approx(1e-6, abs=5e-4)
            assert out["var"][i] >= 0.0

    def test_far_from_data_reverts_to_prior(self):
        # Far from every observation the posterior variance -> prior signal variance.
        out = gp.field({"X": TRAIN_X, "y": TRAIN_Y, "query": [[50.0]], "hyperparams": HP})
        assert out["mean"][0] == pytest.approx(0.0, abs=1e-3)  # zero-mean prior
        assert out["var"][0] == pytest.approx(1.0, abs=1e-3)   # sigma_f^2
        assert out["std"][0] == pytest.approx(1.0, abs=1e-3)

    def test_known_good_interior_point(self):
        # A deterministic regression number: posterior mean at x=2.5 (between samples).
        out = gp.field({"X": TRAIN_X, "y": TRAIN_Y, "query": [[2.5]], "hyperparams": HP})
        # cross-checked against a direct numpy reference computation
        assert out["mean"][0] == pytest.approx(0.5864123102, abs=1e-6)
        assert 0.0 <= out["var"][0] < 0.05  # near data -> small but nonzero
        # std is the sqrt of var
        assert out["std"][0] == pytest.approx(math.sqrt(out["var"][0]), abs=1e-9)

    def test_variance_is_largest_between_sparse_data(self):
        # A coarse training set: variance is biggest in the widest gap.
        X = [[0.0], [1.0], [6.0]]
        y = [0.0, 1.0, 0.5]
        out = gp.field({"X": X, "y": y, "query": [[0.5], [3.5]], "hyperparams": HP})
        assert out["var"][1] > out["var"][0]  # midpoint of the big gap is most uncertain

    def test_norm_cdf_pdf_match_known_values(self):
        z = np.array([0.0, 1.0, -1.0])
        cdf = gp._norm_cdf(z)
        assert cdf[0] == pytest.approx(0.5, abs=1e-9)
        assert cdf[1] == pytest.approx(0.8413447461, abs=1e-9)
        assert cdf[2] == pytest.approx(0.1586552539, abs=1e-9)
        pdf = gp._norm_pdf(np.array([0.0]))
        assert pdf[0] == pytest.approx(1.0 / math.sqrt(2 * math.pi), abs=1e-12)


class TestSuggest:
    def test_ei_prefers_high_uncertainty_or_high_mean(self):
        # Observed y rising toward x=5; EI should pick the unexplored high-x region,
        # which combines high posterior mean AND high uncertainty.
        X = [[0.0], [1.0], [2.0]]
        y = [0.0, 0.4, 0.8]
        candidates = [[0.5], [1.5], [4.0]]
        out = gp.suggest({"X": X, "y": y, "candidates": candidates, "hyperparams": HP})
        assert out["best"] == [4.0]
        assert out["index"] == 2
        assert out["ei"] >= max(out["acquisition"])
        assert out["ei"] > 0.0
        assert len(out["acquisition"]) == 3

    def test_min_goal_flips_the_search(self):
        # For a minimisation goal, the candidate near the lowest observed value/region
        # with room to improve should win; acquisition must still be non-negative.
        X = [[0.0], [1.0], [2.0]]
        y = [0.0, 0.4, 0.8]  # decreasing toward small x
        out = gp.suggest({"X": X, "y": y, "candidates": [[-2.0], [1.5]],
                          "goal": "min", "hyperparams": HP})
        assert out["goal"] == "min"
        assert all(a >= 0.0 for a in out["acquisition"])
        assert out["best"] == [-2.0]  # extrapolating below the data: most improvement

    def test_bounds_grid_candidates(self):
        X = [[0.0], [2.0], [4.0]]
        y = [0.0, 1.0, 0.0]
        out = gp.suggest({"X": X, "y": y, "bounds": [[-1.0, 5.0]], "grid": 25, "hyperparams": HP})
        assert out["n_candidates"] == 25
        assert len(out["acquisition"]) == 25
        assert -1.0 <= out["best"][0] <= 5.0


class TestVerify:
    def test_field_verify_roundtrip_valid(self):
        query = [[1.5], [2.5]]
        f = gp.field({"X": TRAIN_X, "y": TRAIN_Y, "query": query, "hyperparams": HP})
        v = gp.verify({"X": TRAIN_X, "y": TRAIN_Y, "query": query,
                       "claimed_mean": f["mean"], "claimed_var": f["var"], "hyperparams": HP})
        assert v["valid"] is True
        assert v["max_abs_err"] < 1e-6
        assert v["recomputed_mean"] == pytest.approx(f["mean"], abs=1e-9)

    def test_corrupted_mean_invalid(self):
        query = [[1.5], [2.5]]
        f = gp.field({"X": TRAIN_X, "y": TRAIN_Y, "query": query, "hyperparams": HP})
        bad = list(f["mean"])
        bad[0] += 0.5  # tamper
        v = gp.verify({"X": TRAIN_X, "y": TRAIN_Y, "query": query,
                       "claimed_mean": bad, "hyperparams": HP})
        assert v["valid"] is False
        assert v["max_abs_err"] > 0.1


class TestValidationAndClamps:
    def test_missing_fields_raise(self):
        with pytest.raises(ValueError):
            gp.field({"y": [1.0], "query": [[0.0]]})
        with pytest.raises(ValueError):
            gp.field({"X": [[0.0]], "query": [[0.0]]})

    def test_mismatched_lengths_raise(self):
        with pytest.raises(ValueError):
            gp.field({"X": [[0.0], [1.0]], "y": [1.0], "query": [[0.0]]})

    def test_query_dim_mismatch_raises(self):
        with pytest.raises(ValueError):
            gp.field({"X": [[0.0, 1.0]], "y": [1.0], "query": [[0.0]]})

    def test_too_many_observations_clamped(self):
        n = gp.MAX_OBS + 5
        X = [[float(i)] for i in range(n)]
        y = [0.0] * n
        with pytest.raises(ValueError):
            gp.field({"X": X, "y": y, "query": [[0.0]]})


class TestGaussApp:
    @pytest.mark.asyncio
    async def test_field_invoke(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://t") as c:
            r = (await c.post("/ai-market/v2/invoke", json={
                "capability_id": "gauss.field@v1",
                "input": {"X": TRAIN_X, "y": TRAIN_Y, "query": [[2.5]], "hyperparams": HP},
            })).json()
        assert r["ok"] is True
        assert r["output"]["mean"][0] == pytest.approx(0.5864123102, abs=1e-6)
        assert r["output"]["n"] == 6 and r["output"]["d"] == 1

    @pytest.mark.asyncio
    async def test_suggest_invoke(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://t") as c:
            r = (await c.post("/ai-market/v2/invoke", json={
                "capability_id": "gauss.suggest@v1",
                "input": {"X": [[0.0], [1.0], [2.0]], "y": [0.0, 0.4, 0.8],
                          "candidates": [[0.5], [1.5], [4.0]], "hyperparams": HP},
            })).json()
        assert r["ok"] is True
        assert r["output"]["best"] == [4.0]
        assert r["output"]["ei"] > 0.0

    @pytest.mark.asyncio
    async def test_field_then_verify_via_invoke(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://t") as c:
            f = (await c.post("/ai-market/v2/invoke", json={
                "capability_id": "gauss.field@v1",
                "input": {"X": TRAIN_X, "y": TRAIN_Y, "query": [[1.5], [2.5]], "hyperparams": HP},
            })).json()
            assert f["ok"] is True
            out = f["output"]
            v = (await c.post("/ai-market/v2/invoke", json={
                "capability_id": "gauss.verify@v1",
                "input": {"X": TRAIN_X, "y": TRAIN_Y, "query": [[1.5], [2.5]],
                          "claimed_mean": out["mean"], "claimed_var": out["var"], "hyperparams": HP},
            })).json()
        assert v["ok"] is True and v["output"]["valid"] is True

    @pytest.mark.asyncio
    async def test_manifest_signed(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://t") as c:
            m = (await c.get("/ai-market/v2/manifest")).json()
        ids = {t["capability_id"] for t in m["tools"]}
        assert ids == {"gauss.field@v1", "gauss.suggest@v1", "gauss.verify@v1"}
        assert app.state.protocol.signer.verify_manifest_signature(m) is True
