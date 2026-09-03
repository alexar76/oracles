import pytest
from httpx import ASGITransport, AsyncClient

from fermat import eikonal as ek
from fermat.main import app


# ---------------------------------------------------------------------------
# Fixtures: small graphs whose optima are known by hand.
# ---------------------------------------------------------------------------
def diamond():
    # s -> a -> t  (1 + 1 = 2)   vs   s -> b -> t  (1 + 5 = 6)   vs  s -> t (10)
    # optimal: s -> a -> t with total 2.
    return [
        ["s", "a", 1.0], ["a", "t", 1.0],
        ["s", "b", 1.0], ["b", "t", 5.0],
        ["s", "t", 10.0],
    ]


def grid_line():
    # straight chain 0->1->2->3 each weight 2; only one path.
    return [[str(i), str(i + 1), 2.0] for i in range(3)]


def pipeline_dicts():
    # dict-shaped edges with cost/latency/reputation components.
    return [
        {"from": "ingest", "to": "clean", "cost": 0.01, "latency": 100, "reputation": 0.99},
        {"from": "clean", "to": "model", "cost": 0.05, "latency": 400, "reputation": 0.95},
        {"from": "ingest", "to": "model", "cost": 0.20, "latency": 50, "reputation": 0.40},
        {"from": "model", "to": "report", "cost": 0.02, "latency": 80, "reputation": 0.98},
    ]


# ---------------------------------------------------------------------------
# Canonicalisation + commitment
# ---------------------------------------------------------------------------
class TestCanonical:
    def test_commitment_stable_across_edge_order(self):
        e1 = diamond()
        e2 = list(reversed(diamond()))
        c1 = ek.canonical_graph(None, e1, ek.DEFAULT_BLEND)[4]
        c2 = ek.canonical_graph(None, e2, ek.DEFAULT_BLEND)[4]
        assert c1 == c2

    def test_parallel_edges_collapse_to_cheapest(self):
        single = ek.canonical_graph(None, [["a", "b", 3.0]], ek.DEFAULT_BLEND)
        para = ek.canonical_graph(None, [["a", "b", 9.0], ["a", "b", 3.0]], ek.DEFAULT_BLEND)
        # Same canonical edge set (cheapest kept) => same commitment.
        assert single[4] == para[4]

    def test_self_loops_dropped(self):
        base = ek.canonical_graph(None, [["a", "b", 1.0]], ek.DEFAULT_BLEND)
        looped = ek.canonical_graph(None, [["a", "b", 1.0], ["a", "a", 1.0]], ek.DEFAULT_BLEND)
        assert base[4] == looped[4]

    def test_empty_graph_rejected(self):
        with pytest.raises(ValueError):
            ek.canonical_graph(None, [], ek.DEFAULT_BLEND)

    def test_negative_weight_rejected(self):
        with pytest.raises(ValueError):
            ek.canonical_graph(None, [["a", "b", -1.0]], ek.DEFAULT_BLEND)

    def test_node_cap_enforced(self):
        with pytest.raises(ValueError):
            ek.canonical_graph(list(range(ek.MAX_NODES + 5)), [["0", "1", 1.0]], ek.DEFAULT_BLEND)


# ---------------------------------------------------------------------------
# Route correctness — known optima
# ---------------------------------------------------------------------------
class TestRoute:
    def test_diamond_optimum(self):
        out = ek.route(None, diamond(), "s", "t")
        assert out["path"] == ["s", "a", "t"]
        assert out["total"] == 2.0
        assert out["reachable"] is True

    def test_potentials_satisfy_eikonal(self):
        # T(t) = min over incoming of T(u)+n: here via a => 1+1 = 2.
        out = ek.route(None, diamond(), "s", "t")
        T = out["potentials"]
        assert T["s"] == 0.0
        assert T["a"] == 1.0
        assert T["t"] == 2.0

    def test_unreachable_goal(self):
        out = ek.route(None, [["a", "b", 1.0]], "b", "a")  # no edge b->a
        assert out["reachable"] is False
        assert out["path"] is None
        assert out["total"] is None
        assert out["potentials"]["a"] is None

    def test_dict_edges_blend(self):
        out = ek.route(None, pipeline_dicts(), "ingest", "report")
        # ingest->clean->model->report should beat the low-reputation direct ingest->model.
        assert out["path"] == ["ingest", "clean", "model", "report"]
        assert out["reachable"] is True

    def test_blend_reweights_route(self):
        # If we zero out cost & latency and weight only reputation, the high-rep chain wins;
        # if we weight only cost, the cheap-but-risky direct hop becomes attractive.
        rep_only = ek.route(None, pipeline_dicts(), "ingest", "model",
                            blend={"cost": 0.0, "latency": 0.0, "reputation": 1.0})
        assert rep_only["path"] == ["ingest", "clean", "model"]

    def test_start_not_in_graph(self):
        with pytest.raises(ValueError):
            ek.route(None, diamond(), "zzz", "t")

    def test_determinism(self):
        a = ek.route(None, diamond(), "s", "t")
        b = ek.route(None, diamond(), "s", "t")
        assert a["graph_commitment"] == b["graph_commitment"]
        assert a["path"] == b["path"]
        assert a["potentials"] == b["potentials"]


# ---------------------------------------------------------------------------
# The verifiable property — DUAL certificate.
# ---------------------------------------------------------------------------
class TestVerifyCertificate:
    def test_roundtrip_valid(self):
        out = ek.route(None, diamond(), "s", "t")
        v = ek.verify(None, diamond(), out["path"], out["potentials"], "s", "t", total=out["total"])
        assert v["valid"] is True
        assert v["feasible"] is True
        assert v["tight"] is True
        assert v["source_grounded"] is True
        assert v["graph_commitment"] == out["graph_commitment"]
        assert v["recomputed_total"] == out["total"]

    def test_inflated_potentials_break_feasibility(self):
        # Feasibility is T(v) <= T(u) + n(u,v). RAISING the goal's potential makes the
        # LHS of every incoming edge larger: edge a->t now claims T(t)=8 <= T(a)+n=2,
        # which is false. A claimed potential that exceeds the real shortest distance
        # cannot be dual-feasible.
        out = ek.route(None, diamond(), "s", "t")
        bad = dict(out["potentials"])
        bad["t"] = 8.0
        v = ek.verify(None, diamond(), out["path"], bad, "s", "t")
        assert v["feasible"] is False
        assert v["valid"] is False
        assert v["first_violation"] is not None

    def test_deflated_potentials_break_tightness(self):
        # LOWERING T(t) keeps feasibility (a smaller LHS only makes T(v) <= T(u)+n
        # easier), but the claimed path edge a->t is no longer tight
        # (T(t)=0 != T(a)+n=2), so the path does not realise its potential => not optimal.
        out = ek.route(None, diamond(), "s", "t")
        low = dict(out["potentials"])
        low["t"] = 0.0
        v = ek.verify(None, diamond(), out["path"], low, "s", "t")
        assert v["feasible"] is True       # smaller potentials stay dual-feasible
        assert v["tight"] is False         # path no longer realises its potential
        assert v["valid"] is False

    def test_suboptimal_path_rejected(self):
        # Feed the CORRECT optimal potentials but a SUBOPTIMAL path (s->b->t, total 6).
        out = ek.route(None, diamond(), "s", "t")
        v = ek.verify(None, diamond(), ["s", "b", "t"], out["potentials"], "s", "t")
        # s->b is tight (T[b]=1=0+1) but b->t is NOT (T[t]=2 != T[b]+5=6) => tight fails.
        assert v["tight"] is False
        assert v["valid"] is False

    def test_path_not_in_graph_rejected(self):
        out = ek.route(None, diamond(), "s", "t")
        v = ek.verify(None, diamond(), ["s", "t"], out["potentials"], "s", "t")
        # direct s->t edge exists (weight 10) but is not tight against optimal T(t)=2.
        assert v["tight"] is False
        assert v["valid"] is False

    def test_ungrounded_source_rejected(self):
        out = ek.route(None, diamond(), "s", "t")
        bad = dict(out["potentials"])
        bad["s"] = 1.0  # T(start) must be 0
        v = ek.verify(None, diamond(), out["path"], bad, "s", "t")
        assert v["source_grounded"] is False
        assert v["valid"] is False

    def test_wrong_total_rejected(self):
        out = ek.route(None, diamond(), "s", "t")
        v = ek.verify(None, diamond(), out["path"], out["potentials"], "s", "t", total=99.0)
        assert v["valid"] is False

    def test_verify_is_independent_of_oracle_compute(self):
        # A hand-built optimal certificate for the straight chain verifies without
        # the oracle ever having produced it.
        edges = grid_line()  # 0->1->2->3 each weight 2
        T = {"0": 0.0, "1": 2.0, "2": 4.0, "3": 6.0}
        v = ek.verify(None, edges, ["0", "1", "2", "3"], T, "0", "3", total=6.0)
        assert v["valid"] is True


# ---------------------------------------------------------------------------
# ASGI invoke + manifest
# ---------------------------------------------------------------------------
class TestApp:
    async def test_invoke_route(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://t") as client:
            r = await client.post(
                "/ai-market/v2/invoke",
                json={"capability_id": "fermat.route@v1",
                      "input": {"edges": diamond(), "start": "s", "goal": "t"}},
            )
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True
        out = body["output"]
        assert out["path"] == ["s", "a", "t"]
        assert out["total"] == 2.0
        assert "graph_commitment" in out
        assert out["certificate"]["path_edges"]
        assert body["receipt"]  # signed envelope present

    async def test_invoke_route_then_verify(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://t") as client:
            r1 = await client.post(
                "/ai-market/v2/invoke",
                json={"capability_id": "fermat.route@v1",
                      "input": {"edges": diamond(), "start": "s", "goal": "t"}},
            )
            out = r1.json()["output"]
            r2 = await client.post(
                "/ai-market/v2/invoke",
                json={"capability_id": "fermat.verify@v1",
                      "input": {"edges": diamond(), "path": out["path"],
                                "potentials": out["potentials"], "start": "s", "goal": "t",
                                "total": out["total"]}},
            )
        body = r2.json()
        assert body["ok"] is True
        assert body["output"]["valid"] is True
        assert body["output"]["graph_commitment"] == out["graph_commitment"]

    async def test_manifest_lists_capabilities(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://t") as client:
            r = await client.get("/ai-market/v2/manifest")
        ids = {t["capability_id"] for t in r.json()["tools"]}
        assert ids == {"fermat.route@v1", "fermat.verify@v1"}
