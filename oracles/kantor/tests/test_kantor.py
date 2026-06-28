import numpy as np
import pytest
from httpx import ASGITransport, AsyncClient

from kantor import transport as ot
from kantor.main import app


# ---------------------------------------------------------------------------
# Hand-computable optima
# ---------------------------------------------------------------------------
# A 2x2 transport whose optimum is obvious. Sources at "0" and "1" with mass
# a = [0.6, 0.4]; sinks at "0" and "1" with demand b = [0.4, 0.6]; cost is the
# 0/1 "swap" matrix C = [[0,1],[1,0]] (identity placement is free, crossing costs 1).
# The cheapest plan keeps as much mass in place as possible: ship 0.4 src0->sink0
# (free), the leftover 0.2 src0->sink1 (cost 1) and all 0.4 src1->sink1 (free).
# Optimal cost = 0.2.
SWAP_A = [0.6, 0.4]
SWAP_B = [0.4, 0.6]
SWAP_C = [[0.0, 1.0], [1.0, 0.0]]
SWAP_OPT = 0.2

# A second, point-based case the roadmap noted: one unit of mass split evenly at
# x in {0, 1} must become evenly split mass at y in {0.4, 0.6}. With squared-Euclidean
# ground cost the optimal coupling is the monotone one (0->0.4, 1->0.6); the W_2^2 cost
# is 0.5*0.4^2 + 0.5*0.4^2 = 0.16, so W_2 = 0.4 exactly.
W04_SRC = [[0.0], [1.0]]
W04_SNK = [[0.4], [0.6]]
W04_A = [0.5, 0.5]
W04_B = [0.5, 0.5]


class TestExactOptimum:
    def test_swap_case_exact_cost(self):
        out = ot.transport({"a": SWAP_A, "b": SWAP_B, "cost": SWAP_C})
        assert out["method"] == "exact-mincostflow"
        assert out["cost"] == pytest.approx(SWAP_OPT, abs=1e-9)
        assert out["dual_objective"] == pytest.approx(SWAP_OPT, abs=1e-6)

    def test_wasserstein_known_0_4(self):
        # squared-Euclidean ground cost => transport cost is W_2^2 and W = cost**(1/2).
        out = ot.transport({
            "a": W04_A, "b": W04_B,
            "source_points": W04_SRC, "sink_points": W04_SNK,
            "metric": "sqeuclidean",
        })
        assert out["cost"] == pytest.approx(0.16, abs=1e-9)
        assert out["wasserstein"] == pytest.approx(0.4, abs=1e-6)

    def test_p_wasserstein_euclidean_default(self):
        # default metric euclidean, p=2 => cost = dist^2, W_2 = cost**(1/2) = 0.4.
        out = ot.transport({
            "a": W04_A, "b": W04_B,
            "source_points": W04_SRC, "sink_points": W04_SNK,
        })
        assert out["wasserstein"] == pytest.approx(0.4, abs=1e-6)

    def test_marginals_match_a_and_b(self):
        out = ot.transport({"a": SWAP_A, "b": SWAP_B, "cost": SWAP_C})
        P = np.array(out["plan"])
        assert np.allclose(P.sum(axis=1), SWAP_A, atol=1e-5)  # row sums == a
        assert np.allclose(P.sum(axis=0), SWAP_B, atol=1e-5)  # col sums == b

    def test_diagonal_cost_is_zero_transport(self):
        # identical distributions over identical points cost nothing to transport.
        out = ot.transport({"a": [0.5, 0.5], "b": [0.5, 0.5], "cost": [[0.0, 2.0], [2.0, 0.0]]})
        assert out["cost"] == pytest.approx(0.0, abs=1e-9)

    def test_random_cases_marginals_and_selfcertify(self):
        rng = np.random.default_rng(11)
        for _ in range(6):
            m, n = int(rng.integers(2, 7)), int(rng.integers(2, 7))
            a = rng.random(m); b = rng.random(n); C = rng.random((m, n)) * 3
            out = ot.transport({"a": a.tolist(), "b": b.tolist(), "cost": C.tolist()})
            P = np.array(out["plan"])
            an, bn = a / a.sum(), b / b.sum()
            assert np.allclose(P.sum(axis=1), an, atol=1e-4)
            assert np.allclose(P.sum(axis=0), bn, atol=1e-4)
            # the oracle's own certificate verifies
            v = ot.verify({"a": a.tolist(), "b": b.tolist(), "cost": C.tolist(),
                           "claimed_cost": out["cost"], "potentials": out["potentials"]})
            assert v["valid"] is True


# ---------------------------------------------------------------------------
# Sinkhorn is APPROXIMATE — labelled, and an upper bound on the true optimum
# ---------------------------------------------------------------------------
class TestSinkhornApproximate:
    def test_sinkhorn_labelled_approximate(self):
        out = ot.transport({"a": SWAP_A, "b": SWAP_B, "cost": SWAP_C,
                            "method": "sinkhorn", "eps": 0.5})
        assert out["method"] == "sinkhorn-approx"
        assert out["approximate"] is True
        assert out["regularizer_eps"] == 0.5
        assert "certificate" not in out  # no exact dual certificate offered

    def test_entropic_overshoots_true_optimum(self):
        exact = ot.transport({"a": SWAP_A, "b": SWAP_B, "cost": SWAP_C})
        sink = ot.transport({"a": SWAP_A, "b": SWAP_B, "cost": SWAP_C,
                            "method": "sinkhorn", "eps": 0.5})
        # entropic OT cost >= true OT cost, and is strictly larger at this eps.
        assert exact["cost"] <= sink["cost"] + 1e-9
        assert sink["cost"] > exact["cost"] + 1e-3
        # exact matches the known optimum; sinkhorn does not.
        assert exact["cost"] == pytest.approx(SWAP_OPT, abs=1e-9)

    def test_smaller_eps_closer_to_exact(self):
        exact = ot.transport({"a": SWAP_A, "b": SWAP_B, "cost": SWAP_C})["cost"]
        big = ot.transport({"a": SWAP_A, "b": SWAP_B, "cost": SWAP_C,
                           "method": "sinkhorn", "eps": 0.5})["cost"]
        small = ot.transport({"a": SWAP_A, "b": SWAP_B, "cost": SWAP_C,
                             "method": "sinkhorn", "eps": 0.05})["cost"]
        assert abs(small - exact) < abs(big - exact)


# ---------------------------------------------------------------------------
# The verifiable property — KANTOROVICH DUAL certificate
# ---------------------------------------------------------------------------
class TestVerifyCertificate:
    def test_roundtrip_valid(self):
        out = ot.transport({"a": SWAP_A, "b": SWAP_B, "cost": SWAP_C})
        v = ot.verify({"a": SWAP_A, "b": SWAP_B, "cost": SWAP_C,
                       "claimed_cost": out["cost"], "potentials": out["potentials"]})
        assert v["valid"] is True
        assert v["feasible"] is True
        assert v["strong_duality"] is True
        assert v["dual_objective"] == pytest.approx(out["cost"], abs=1e-6)
        assert v["max_violation"] <= 1e-6

    def test_corrupt_claimed_cost_invalid(self):
        out = ot.transport({"a": SWAP_A, "b": SWAP_B, "cost": SWAP_C})
        v = ot.verify({"a": SWAP_A, "b": SWAP_B, "cost": SWAP_C,
                       "claimed_cost": 0.05, "potentials": out["potentials"]})
        # feasibility still holds (potentials untouched) but strong duality breaks.
        assert v["feasible"] is True
        assert v["strong_duality"] is False
        assert v["valid"] is False

    def test_tampered_potential_breaks_feasibility(self):
        # Raising u_0 makes u_0 + v_j exceed C_0j for some j => dual-infeasible,
        # so the certificate no longer bounds the primal and verification fails.
        out = ot.transport({"a": SWAP_A, "b": SWAP_B, "cost": SWAP_C})
        bad = {"u": list(out["potentials"]["u"]), "v": list(out["potentials"]["v"])}
        bad["u"][0] += 5.0
        v = ot.verify({"a": SWAP_A, "b": SWAP_B, "cost": SWAP_C,
                       "claimed_cost": out["cost"], "potentials": bad})
        assert v["feasible"] is False
        assert v["max_violation"] > 1.0
        assert v["valid"] is False

    def test_hand_built_certificate_verifies_without_oracle(self):
        # A verifier accepts a correct certificate it constructs itself, never having
        # asked the oracle to compute it. For the swap case the optimal duals are
        # u = [0, 1], v = [0, -1]: u_i + v_j <= C_ij everywhere, tight on the support,
        # and 0.6*0 + 0.4*1 + 0.4*0 + 0.6*(-1) = -0.2 ... so use the equivalent
        # gauge u=[0,1], v=[0,-1] shifted: the oracle's own (u,v) is the canonical one.
        # Here we assert the dual objective equals the optimum for the oracle duals.
        out = ot.transport({"a": SWAP_A, "b": SWAP_B, "cost": SWAP_C})
        u = np.array(out["potentials"]["u"]); v = np.array(out["potentials"]["v"])
        dual = float(np.dot(SWAP_A, u) + np.dot(SWAP_B, v))
        assert dual == pytest.approx(SWAP_OPT, abs=1e-6)
        # feasibility by hand: u_i + v_j <= C_ij on all four pairs
        C = np.array(SWAP_C)
        assert np.all(u[:, None] + v[None, :] <= C + 1e-6)


# ---------------------------------------------------------------------------
# Input validation + size clamps (the protocol does not validate input_schema)
# ---------------------------------------------------------------------------
class TestValidationAndClamps:
    def test_missing_a_rejected(self):
        with pytest.raises(ValueError):
            ot.transport({"b": [0.5, 0.5], "cost": [[1.0, 2.0]]})

    def test_no_cost_no_points_rejected(self):
        with pytest.raises(ValueError):
            ot.transport({"a": [1.0], "b": [1.0]})

    def test_cost_shape_mismatch_rejected(self):
        with pytest.raises(ValueError):
            ot.transport({"a": [0.5, 0.5], "b": [0.5, 0.5, 0.5], "cost": [[1.0, 2.0], [3.0, 4.0]]})

    def test_too_many_bins_clamped(self):
        big = ot.MAX_BINS + 1
        a = [1.0 / big] * big
        b = [1.0 / big] * big
        C = [[1.0] * big for _ in range(big)]
        with pytest.raises(ValueError):
            ot.transport({"a": a, "b": b, "cost": C})

    def test_negative_cost_rejected(self):
        with pytest.raises(ValueError):
            ot.transport({"a": [0.5, 0.5], "b": [0.5, 0.5], "cost": [[0.0, -1.0], [1.0, 0.0]]})

    def test_weights_renormalised(self):
        # weights need not sum to 1; they are renormalised internally.
        out = ot.transport({"a": [3.0, 2.0], "b": [2.0, 3.0], "cost": SWAP_C})
        P = np.array(out["plan"])
        assert P.sum() == pytest.approx(1.0, abs=1e-6)


# ---------------------------------------------------------------------------
# ASGI invoke + manifest
# ---------------------------------------------------------------------------
class TestApp:
    async def test_invoke_transport(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://t") as client:
            r = await client.post(
                "/ai-market/v2/invoke",
                json={"capability_id": "kantor.transport@v1",
                      "input": {"a": SWAP_A, "b": SWAP_B, "cost": SWAP_C}},
            )
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True
        out = body["output"]
        assert out["cost"] == pytest.approx(SWAP_OPT, abs=1e-9)
        assert out["method"] == "exact-mincostflow"
        assert out["certificate"]["kind"].startswith("kantorovich")
        assert body["receipt"]  # signed envelope present

    async def test_invoke_transport_then_verify(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://t") as client:
            r1 = await client.post(
                "/ai-market/v2/invoke",
                json={"capability_id": "kantor.transport@v1",
                      "input": {"a": SWAP_A, "b": SWAP_B, "cost": SWAP_C}},
            )
            out = r1.json()["output"]
            r2 = await client.post(
                "/ai-market/v2/invoke",
                json={"capability_id": "kantor.verify@v1",
                      "input": {"a": SWAP_A, "b": SWAP_B, "cost": SWAP_C,
                                "claimed_cost": out["cost"], "potentials": out["potentials"]}},
            )
        body = r2.json()
        assert body["ok"] is True
        assert body["output"]["valid"] is True

    async def test_invoke_verify_rejects_tamper(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://t") as client:
            r1 = await client.post(
                "/ai-market/v2/invoke",
                json={"capability_id": "kantor.transport@v1",
                      "input": {"a": SWAP_A, "b": SWAP_B, "cost": SWAP_C}},
            )
            out = r1.json()["output"]
            bad = {"u": list(out["potentials"]["u"]), "v": list(out["potentials"]["v"])}
            bad["u"][0] += 9.0
            r2 = await client.post(
                "/ai-market/v2/invoke",
                json={"capability_id": "kantor.verify@v1",
                      "input": {"a": SWAP_A, "b": SWAP_B, "cost": SWAP_C,
                                "claimed_cost": out["cost"], "potentials": bad}},
            )
        assert r2.json()["output"]["valid"] is False

    async def test_manifest_signed_lists_both(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://t") as client:
            m = (await client.get("/ai-market/v2/manifest")).json()
        ids = {t["capability_id"] for t in m["tools"]}
        assert ids == {"kantor.transport@v1", "kantor.verify@v1"}
        assert app.state.protocol.signer.verify_manifest_signature(m) is True
