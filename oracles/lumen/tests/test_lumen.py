import numpy as np
import pytest
from httpx import ASGITransport, AsyncClient

from lumen import pagerank
from lumen.main import app


class TestTransitionMatrix:
    def test_columns_are_stochastic(self):
        # 3 nodes, a couple of weighted trust edges.
        M = pagerank.build_transition_matrix(3, [[0, 1, 2.0], [0, 2, 2.0], [1, 2, 1.0]])
        col_sums = M.sum(axis=0)
        assert np.allclose(col_sums, 1.0, atol=1e-12)
        # Node 0 split its trust 50/50 between 1 and 2.
        assert M[1, 0] == pytest.approx(0.5)
        assert M[2, 0] == pytest.approx(0.5)

    def test_dangling_node_becomes_uniform_column(self):
        # Node 2 has no outgoing edges -> its column must be uniform 1/n.
        M = pagerank.build_transition_matrix(3, [[0, 1, 1.0], [1, 0, 1.0]])
        assert np.allclose(M[:, 2], 1.0 / 3.0)
        assert np.allclose(M.sum(axis=0), 1.0)

    def test_bad_edge_shape_rejected(self):
        with pytest.raises(ValueError):
            pagerank.build_transition_matrix(2, [[0, 1]])

    def test_out_of_range_endpoint_rejected(self):
        with pytest.raises(ValueError):
            pagerank.build_transition_matrix(2, [[0, 5, 1.0]])

    def test_negative_weight_rejected(self):
        with pytest.raises(ValueError):
            pagerank.build_transition_matrix(2, [[0, 1, -1.0]])


class TestPageRank:
    def test_scores_sum_to_one(self):
        out = pagerank.pagerank(5, [[0, 1, 1.0], [1, 2, 1.0], [2, 3, 1.0], [3, 4, 1.0]])
        assert abs(sum(out["scores"]) - 1.0) < 1e-6
        assert all(s >= 0 for s in out["scores"])

    def test_most_trusted_node_wins(self):
        # Everyone trusts node 3; node 3 trusts node 4 (so 4 inherits 3's high rank).
        # Authority hub (3) should clearly outrank the leaf voters (0,1,2).
        edges = [[0, 3, 1.0], [1, 3, 1.0], [2, 3, 1.0], [4, 3, 1.0]]
        out = pagerank.pagerank(5, edges)
        scores = out["scores"]
        top = int(np.argmax(scores))
        assert top == 3
        # The hub everyone points at beats each individual voter.
        for voter in (0, 1, 2, 4):
            assert scores[3] > scores[voter]

    def test_transitive_trust_beats_direct(self):
        # Classic chain: 0->1, 1->2, 2->0 plus extra votes funnelled to node 2.
        edges = [[0, 1, 1.0], [1, 2, 1.0], [2, 0, 1.0], [3, 2, 1.0], [4, 2, 1.0]]
        out = pagerank.pagerank(5, edges)
        scores = out["scores"]
        # Node 2 receives the most (and most-trusted) inbound trust -> top score.
        assert int(np.argmax(scores)) == 2

    def test_power_iteration_converges(self):
        out = pagerank.pagerank(6, [[0, 1, 1.0], [1, 2, 1.0], [2, 0, 1.0], [3, 1, 1.0], [4, 2, 1.0], [5, 0, 1.0]], tol=1e-12)
        assert out["converged"] is True
        assert out["iterations"] < pagerank.DEFAULT_MAX_ITER

    def test_converged_vector_is_fixed_point(self):
        # The returned vector r must satisfy r ≈ G·r (it is the dominant eigenvector).
        n = 5
        edges = [[0, 1, 2.0], [1, 2, 1.0], [2, 3, 1.0], [3, 4, 1.0], [4, 0, 1.0], [0, 3, 1.0]]
        damping = 0.85
        out = pagerank.pagerank(n, edges, damping=damping, tol=1e-13)
        r = np.array(out["scores"])
        M = pagerank.build_transition_matrix(n, edges)
        Gr = damping * (M @ r) + (1.0 - damping) / n
        assert np.allclose(Gr, r, atol=1e-8)

    def test_dangling_node_handled(self):
        # Node 2 is a sink (no outgoing trust). PageRank must still sum to 1 and the
        # sink, which everyone points at, should accumulate the most rank.
        edges = [[0, 2, 1.0], [1, 2, 1.0], [0, 1, 1.0]]
        out = pagerank.pagerank(3, edges)
        assert abs(sum(out["scores"]) - 1.0) < 1e-6
        assert int(np.argmax(out["scores"])) == 2

    def test_symmetric_graph_gives_uniform_scores(self):
        # A complete symmetric trust graph -> every node is identical -> uniform scores.
        edges = []
        for i in range(4):
            for j in range(4):
                if i != j:
                    edges.append([i, j, 1.0])
        out = pagerank.pagerank(4, edges)
        assert np.allclose(out["scores"], 0.25, atol=1e-6)

    def test_damping_must_be_open_interval(self):
        with pytest.raises(ValueError):
            pagerank.pagerank(3, [[0, 1, 1.0]], damping=1.0)
        with pytest.raises(ValueError):
            pagerank.pagerank(3, [[0, 1, 1.0]], damping=0.0)

    def test_no_edges_is_uniform(self):
        out = pagerank.pagerank(4, [])
        assert np.allclose(out["scores"], 0.25, atol=1e-6)
        assert abs(sum(out["scores"]) - 1.0) < 1e-6


class TestLumenApp:
    @pytest.mark.asyncio
    async def test_reputation_via_invoke(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://t") as c:
            payload = {
                "capability_id": "lumen.reputation@v1",
                "input": {
                    "nodes": 5,
                    "edges": [[0, 3, 1.0], [1, 3, 1.0], [2, 3, 1.0], [4, 3, 1.0]],
                    "damping": 0.85,
                },
            }
            resp = (await c.post("/ai-market/v2/invoke", json=payload)).json()
            assert resp["ok"] is True
            out = resp["output"]
            assert len(out["scores"]) == 5
            assert abs(sum(out["scores"]) - 1.0) < 1e-6
            assert out["converged"] is True
            assert int(np.argmax(out["scores"])) == 3
            # Envelope carries a signed receipt + provenance.
            assert "receipt" in resp and "provenance" in resp
            assert resp["provenance"]["source"] == "prod-lumen"

    @pytest.mark.asyncio
    async def test_unknown_capability_is_error(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://t") as c:
            resp = (await c.post("/ai-market/v2/invoke", json={"capability_id": "lumen.nope@v9", "input": {}})).json()
            assert resp["ok"] is False

    @pytest.mark.asyncio
    async def test_manifest_signed(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://t") as c:
            m = (await c.get("/ai-market/v2/manifest")).json()
        ids = {t["capability_id"] for t in m["tools"]}
        assert ids == {"lumen.reputation@v1", "lumen.score@v1", "lumen.verify@v1"}
        assert app.state.protocol.signer.verify_manifest_signature(m) is True

    @pytest.mark.asyncio
    async def test_score_and_verify_via_invoke(self):
        transport = ASGITransport(app=app)
        edges = [[0, 3, 1.0], [1, 3, 1.0], [2, 3, 1.0], [4, 3, 1.0]]
        async with AsyncClient(transport=transport, base_url="http://t") as c:
            rep = (await c.post(
                "/ai-market/v2/invoke",
                json={"capability_id": "lumen.reputation@v1", "input": {"nodes": 5, "edges": edges}},
            )).json()
            assert rep["ok"] is True
            scores = rep["output"]["scores"]
            score = (await c.post(
                "/ai-market/v2/invoke",
                json={
                    "capability_id": "lumen.score@v1",
                    "input": {"nodes": 5, "edges": edges, "target_node": 3},
                },
            )).json()
            assert score["ok"] is True
            assert score["output"]["rank"] == 1
            assert score["output"]["score"] == pytest.approx(scores[3])
            verify = (await c.post(
                "/ai-market/v2/invoke",
                json={
                    "capability_id": "lumen.verify@v1",
                    "input": {"nodes": 5, "edges": edges, "scores": scores},
                },
            )).json()
            assert verify["ok"] is True
            assert verify["output"]["valid"] is True

    @pytest.mark.asyncio
    async def test_health_and_well_known(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://t") as c:
            h = (await c.get("/api/health")).json()
            assert h["status"] == "ok"
            wk = (await c.get("/.well-known/ai-market.json")).json()
            assert wk["capabilities_count"] == 3
            assert "signer_public_key" in wk
