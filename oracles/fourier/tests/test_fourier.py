import math

import pytest
from httpx import ASGITransport, AsyncClient

from fourier import spectral
from fourier.main import app


# ----------------------------- graph builders -----------------------------
def path_graph(n):
    """Path P_n: 0-1-2-...-(n-1)."""
    return [[i, i + 1] for i in range(n - 1)]


def cycle_graph(n):
    """Cycle C_n: closes the path back to 0."""
    return [[i, (i + 1) % n] for i in range(n)]


def two_cliques_bridge():
    """Two K5 cliques {0..4} and {5..9} joined by the SINGLE bridge edge (4,5)."""
    a = [[i, j] for i in range(5) for j in range(i + 1, 5)]
    b = [[i, j] for i in range(5, 10) for j in range(i + 1, 10)]
    return a + b + [[4, 5]]


def two_components():
    """Two disjoint triangles {0,1,2} and {3,4,5} — a disconnected graph."""
    return [[0, 1], [1, 2], [2, 0], [3, 4], [4, 5], [5, 3]]


# ----------------------------- known spectra ------------------------------
class TestKnownSpectra:
    def test_cycle_combinatorial_eigenvalues(self):
        # C_n combinatorial Laplacian spectrum: 2 - 2cos(2πk/n), k = 0..n-1.
        n = 8
        out = spectral.analyze(None, cycle_graph(n), laplacian_kind="combinatorial", k=n)
        expected = sorted(2 - 2 * math.cos(2 * math.pi * k / n) for k in range(n))
        for got, exp in zip(out["eigenvalues"], expected):
            assert got == pytest.approx(exp, abs=1e-9)
        # λ2 of C_8 = 2 - 2cos(2π/8) = 2 - √2.
        assert out["fiedler_value"] == pytest.approx(2 - math.sqrt(2), abs=1e-9)

    def test_path_lambda1_is_zero_lambda2_positive(self):
        # A connected path: λ1 = 0 (always), λ2 > 0. Combinatorial λ2(P_n)=2(1-cos(π/n)).
        n = 6
        out = spectral.analyze(None, path_graph(n), laplacian_kind="combinatorial", k=n)
        assert out["eigenvalues"][0] == pytest.approx(0.0, abs=1e-9)
        assert out["fiedler_value"] == pytest.approx(2 * (1 - math.cos(math.pi / n)), abs=1e-9)

    def test_normalized_spectrum_bounded(self):
        # Normalized Laplacian eigenvalues live in [0, 2].
        out = spectral.analyze(None, cycle_graph(10), laplacian_kind="normalized", k=10)
        assert min(out["eigenvalues"]) >= -1e-9
        assert max(out["eigenvalues"]) <= 2 + 1e-9
        assert out["eigenvalues"][0] == pytest.approx(0.0, abs=1e-9)


class TestNearSplit:
    def test_two_cliques_small_lambda2_and_clean_cut(self):
        out = spectral.analyze(None, two_cliques_bridge(), laplacian_kind="combinatorial", k=10)
        # A single bridge between two dense cliques ⇒ a narrow bottleneck ⇒ small λ2.
        assert 0.0 < out["fiedler_value"] < 1.0
        cut = out["spectral_cut"]
        clique_a, clique_b = {"0", "1", "2", "3", "4"}, {"5", "6", "7", "8", "9"}
        set_a, set_b = set(cut["set_a"]), set(cut["set_b"])
        # The Fiedler bisection separates the two cliques exactly (either labelling).
        assert (set_a == clique_a and set_b == clique_b) or (set_a == clique_b and set_b == clique_a)
        # Only the single bridge edge crosses the cut.
        assert cut["cut_size"] == pytest.approx(1.0, abs=1e-9)

    def test_disconnected_graph_lambda2_zero(self):
        # Two components ⇒ algebraic connectivity λ2 = 0 (both laplacians).
        comb = spectral.analyze(None, two_components(), laplacian_kind="combinatorial", k=6)
        norm = spectral.analyze(None, two_components(), laplacian_kind="normalized", k=6)
        assert comb["fiedler_value"] == pytest.approx(0.0, abs=1e-9)
        assert norm["fiedler_value"] == pytest.approx(0.0, abs=1e-9)
        assert comb["combinatorial_lambda2"] == pytest.approx(0.0, abs=1e-9)


class TestVerify:
    def test_roundtrip_valid(self):
        # spectrum → verify roundtrip: the returned (λ2, fiedler_vector) certifies True.
        out = spectral.analyze(None, two_cliques_bridge(), laplacian_kind="combinatorial", k=10)
        v = spectral.verify(
            None, two_cliques_bridge(),
            lambda_=out["fiedler_value"], vector=out["fiedler_vector"],
            laplacian_kind="combinatorial",
        )
        assert v["valid"] is True
        assert v["residual"] < 1e-6
        assert v["orthogonality"] < 1e-6
        assert v["graph_commitment"] == out["graph_commitment"]

    def test_wrong_lambda_rejected(self):
        out = spectral.analyze(None, two_cliques_bridge(), laplacian_kind="combinatorial", k=10)
        v = spectral.verify(
            None, two_cliques_bridge(),
            lambda_=out["fiedler_value"] + 0.5, vector=out["fiedler_vector"],
            laplacian_kind="combinatorial",
        )
        assert v["valid"] is False
        assert v["is_eigenpair"] is False

    def test_trivial_vector_flagged_not_orthogonal(self):
        # The all-ones vector IS an eigenpair (λ=0 for combinatorial) but is the trivial
        # λ1 mode — orthogonality against ones is ~1, so it is NOT a valid Fiedler cert.
        edges = two_cliques_bridge()
        ones = [1.0] * 10
        v = spectral.verify(None, edges, lambda_=0.0, vector=ones, laplacian_kind="combinatorial")
        assert v["is_eigenpair"] is True       # L·1 = 0 = λ·1
        assert v["orthogonality"] == pytest.approx(1.0, abs=1e-9)
        assert v["valid"] is False             # rejected: it's the trivial mode

    def test_wrong_length_vector_rejected(self):
        v = spectral.verify(None, cycle_graph(8), lambda_=0.0, vector=[1.0, 2.0], laplacian_kind="combinatorial")
        assert v["valid"] is False
        assert "error" in v


class TestGuards:
    def test_node_cap_enforced(self):
        big = [[i, i + 1] for i in range(spectral.MAX_NODES + 5)]
        with pytest.raises(ValueError):
            spectral.analyze(None, big)

    def test_empty_graph_rejected(self):
        with pytest.raises(ValueError):
            spectral.analyze(None, [])

    def test_weighted_edges_accepted(self):
        out = spectral.analyze(None, [[0, 1, 2.5], [1, 2, 0.5]], laplacian_kind="combinatorial", k=3)
        assert out["n"] == 3 and out["m"] == 2

    def test_commitment_order_independent(self):
        c1 = spectral.canonical_graph(None, [[0, 1], [1, 2], [2, 0]])[3]
        c2 = spectral.canonical_graph(None, [[2, 1], [0, 2], [1, 0]])[3]
        assert c1 == c2


# ------------------------------- app surface ------------------------------
class TestFourierApp:
    @pytest.mark.asyncio
    async def test_spectrum_then_verify_via_invoke(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://t") as c:
            sp = (await c.post(
                "/ai-market/v2/invoke",
                json={"capability_id": "fourier.spectrum@v1",
                      "input": {"edges": two_cliques_bridge(), "laplacian": "combinatorial", "k": 10}},
            )).json()
            assert sp["ok"] is True
            out = sp["output"]
            assert 0.0 < out["fiedler_value"] < 1.0
            assert sp["receipt"]  # signed envelope present

            vr = (await c.post(
                "/ai-market/v2/invoke",
                json={"capability_id": "fourier.verify@v1",
                      "input": {"edges": two_cliques_bridge(), "laplacian": "combinatorial",
                                "lambda": out["fiedler_value"], "vector": out["fiedler_vector"]}},
            )).json()
            assert vr["ok"] is True and vr["output"]["valid"] is True

    @pytest.mark.asyncio
    async def test_verify_rejects_wrong_lambda_via_invoke(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://t") as c:
            sp = (await c.post(
                "/ai-market/v2/invoke",
                json={"capability_id": "fourier.spectrum@v1",
                      "input": {"edges": cycle_graph(8), "laplacian": "combinatorial"}},
            )).json()["output"]
            vr = (await c.post(
                "/ai-market/v2/invoke",
                json={"capability_id": "fourier.verify@v1",
                      "input": {"edges": cycle_graph(8), "laplacian": "combinatorial",
                                "lambda": sp["fiedler_value"] + 1.0, "vector": sp["fiedler_vector"]}},
            )).json()
            assert vr["ok"] is True and vr["output"]["valid"] is False

    @pytest.mark.asyncio
    async def test_missing_edges_is_error_envelope(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://t") as c:
            r = (await c.post(
                "/ai-market/v2/invoke",
                json={"capability_id": "fourier.spectrum@v1", "input": {}},
            )).json()
        assert r["ok"] is False and "edges" in r["error"]

    @pytest.mark.asyncio
    async def test_manifest_signed(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://t") as c:
            m = (await c.get("/ai-market/v2/manifest")).json()
        ids = {t["capability_id"] for t in m["tools"]}
        assert ids == {"fourier.spectrum@v1", "fourier.verify@v1"}
        assert app.state.protocol.signer.verify_manifest_signature(m) is True
