import pytest
from httpx import ASGITransport, AsyncClient

from percola import percolation as pc
from percola.main import app


def ring(n):
    return [[i, (i + 1) % n] for i in range(n)]


def star(n):
    return [[0, i] for i in range(1, n)]


def two_cliques_bridge():
    # Two K4 cliques (0..3) and (4..7) joined only through bridge node 8.
    a = [[i, j] for i in range(4) for j in range(i + 1, 4)]
    b = [[i, j] for i in range(4, 8) for j in range(i + 1, 8)]
    bridge = [[3, 8], [8, 4]]
    return a + b + bridge


class TestCanonicalisation:
    def test_commitment_is_order_independent(self):
        e1 = [[0, 1], [1, 2], [2, 0]]
        e2 = [[2, 1], [0, 2], [1, 0]]  # reversed pairs, shuffled order
        c1 = pc.canonical_graph(None, e1)[4]
        c2 = pc.canonical_graph(None, e2)[4]
        assert c1 == c2

    def test_self_loops_and_duplicates_dropped(self):
        base = pc.canonical_graph(None, [[0, 1], [1, 2]])
        dup = pc.canonical_graph(None, [[0, 1], [1, 0], [1, 2], [2, 2]])
        assert base[4] == dup[4]
        assert base[3] == dup[3]  # identical edge sets

    def test_empty_graph_rejected(self):
        with pytest.raises(ValueError):
            pc.canonical_graph(None, [])

    def test_node_cap_enforced(self):
        with pytest.raises(ValueError):
            pc.canonical_graph(list(range(pc.MAX_NODES + 5)), [[0, 1]])


class TestThreshold:
    def test_star_is_maximally_fragile(self):
        # Removing the single hub fragments everything → f_c ≈ 1/n, hub is the keystone.
        n = 12
        out = pc.analyze(None, star(n), samples=n, attack="targeted")
        assert out["targeted"]["f_c"] <= 2.0 / n
        assert "0" in out["targeted"]["keystones"]

    def test_bridge_region_keystone_triggers_split(self):
        out = pc.analyze(None, two_cliques_bridge(), samples=9, attack="targeted")
        # The structure is fragile at the bridge: a single cut vertex around it
        # ({3, 4} are the clique-side endpoints, 8 the bridge) fragments the graph.
        assert out["targeted"]["f_c"] <= 2.0 / 9
        assert set(out["targeted"]["keystones"]) & {"3", "4", "8"}

    def test_ring_more_robust_than_star(self):
        n = 16
        r = pc.analyze(None, ring(n), samples=n, attack="targeted")["robustness"]
        s = pc.analyze(None, star(n), samples=n, attack="targeted")["robustness"]
        assert r > s

    def test_curve_starts_intact(self):
        out = pc.analyze(None, ring(20), samples=20, attack="targeted")
        first = out["targeted"]["curve"][0]
        assert first["f"] == 0.0
        assert first["p_inf"] == 1.0  # whole graph is one component at f=0

    def test_deterministic_commitment_and_order(self):
        a = pc.analyze(None, two_cliques_bridge(), samples=9, attack="targeted")
        b = pc.analyze(None, two_cliques_bridge(), samples=9, attack="targeted")
        assert a["graph_commitment"] == b["graph_commitment"]
        assert a["targeted"]["order_hash"] == b["targeted"]["order_hash"]
        assert a["targeted"]["f_c"] == b["targeted"]["f_c"]

    def test_random_attack_reproducible_from_seed(self):
        o1 = pc.analyze(None, ring(20), samples=20, attack="random", nonce="abc")
        o2 = pc.analyze(None, ring(20), samples=20, attack="random", nonce="abc")
        assert o1["random"]["seed"] == o2["random"]["seed"]
        assert o1["random"]["order_hash"] == o2["random"]["order_hash"]
        # A different nonce gives a different committed order.
        o3 = pc.analyze(None, ring(20), samples=20, attack="random", nonce="xyz")
        assert o3["random"]["seed"] != o1["random"]["seed"]


class TestVerify:
    def test_roundtrip_valid(self):
        out = pc.analyze(None, two_cliques_bridge(), samples=9, attack="targeted")
        fc = out["targeted"]["f_c"]
        v = pc.verify(None, two_cliques_bridge(), attack="targeted", f_c=fc, samples=9)
        assert v["valid"] is True
        assert v["graph_commitment"] == out["graph_commitment"]
        assert v["recomputed_f_c"] == fc

    def test_wrong_fc_rejected(self):
        out = pc.analyze(None, two_cliques_bridge(), samples=9, attack="targeted")
        v = pc.verify(None, two_cliques_bridge(), attack="targeted", f_c=out["targeted"]["f_c"] + 0.5, samples=9)
        assert v["valid"] is False

    def test_random_verify_with_seed(self):
        out = pc.analyze(None, ring(20), samples=20, attack="random", nonce="abc")
        v = pc.verify(None, ring(20), attack="random", f_c=out["random"]["f_c"],
                      seed=out["random"]["seed"], samples=20)
        assert v["valid"] is True


class TestApp:
    async def test_invoke_threshold(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://t") as client:
            r = await client.post(
                "/ai-market/v2/invoke",
                json={"capability_id": "percola.threshold@v1",
                      "input": {"edges": two_cliques_bridge(), "samples": 9}},
            )
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True
        out = body["output"]
        assert "graph_commitment" in out
        assert 0.0 < out["targeted"]["f_c"] < 1.0
        assert body["receipt"]  # signed envelope present

    async def test_manifest_lists_capabilities(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://t") as client:
            r = await client.get("/ai-market/v2/manifest")
        ids = {t["capability_id"] for t in r.json()["tools"]}
        assert ids == {"percola.threshold@v1", "percola.verify@v1"}
