import random

import pytest
from httpx import ASGITransport, AsyncClient

from ablation import sandpile as sp
from ablation.main import app


# --------------------------------------------------------------------------- #
# Test substrates                                                             #
# --------------------------------------------------------------------------- #

def grid(L):
    """Directed L×L grid (the classic BTW sandpile substrate). Boundary cells have
    fewer out-edges, so the lattice dissipates at its edge — avalanches stay finite and
    the size distribution is heavy-tailed (power-law)."""
    edges = []

    def nid(r, c):
        return f"{r},{c}"

    for r in range(L):
        for c in range(L):
            for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                rr, cc = r + dr, c + dc
                if 0 <= rr < L and 0 <= cc < L:
                    edges.append([nid(r, c), nid(rr, cc)])
    return edges


def two_clusters_bridge():
    """Two dense bidirectional clusters joined only through a single bridge node H."""
    a = [[f"a{i}", f"a{j}"] for i in range(5) for j in range(5) if i != j]
    b = [[f"b{i}", f"b{j}"] for i in range(5) for j in range(5) if i != j]
    bridge = [["a0", "H"], ["H", "b0"], ["b0", "H"], ["H", "a0"]]
    return a + b + bridge


def chain(n):
    """A directed path 0->1->...->(n-1); the last node has no out-edge (dissipates)."""
    return [[i, i + 1] for i in range(n - 1)]


# --------------------------------------------------------------------------- #
# Canonicalisation + commitment                                              #
# --------------------------------------------------------------------------- #

class TestCanonicalisation:
    def test_commitment_is_edge_order_independent(self):
        e = grid(5)
        shuf = e[:]
        random.Random(7).shuffle(shuf)
        c1 = sp.canonical_config(e)["commitment"]
        c2 = sp.canonical_config(shuf)["commitment"]
        assert c1 == c2

    def test_self_loops_and_duplicates_dropped(self):
        base = sp.canonical_config([[0, 1], [1, 2]])
        dup = sp.canonical_config([[0, 1], [0, 1], [1, 2], [2, 2]])  # dup edge + self-loop
        assert base["commitment"] == dup["commitment"]
        assert base["m"] == dup["m"]

    def test_direction_matters(self):
        # Directed graph: [u,v] != [v,u]; the two configs must differ.
        c1 = sp.canonical_config([[0, 1]])["commitment"]
        c2 = sp.canonical_config([[1, 0]])["commitment"]
        assert c1 != c2

    def test_empty_graph_rejected(self):
        with pytest.raises(ValueError):
            sp.canonical_config([])

    def test_node_cap_enforced(self):
        with pytest.raises(ValueError):
            sp.canonical_config([[0, 1]], nodes=list(range(sp.MAX_NODES + 5)))

    def test_default_threshold_is_out_degree_plus_dissipation(self):
        # Open-boundary BTW default: capacity = out_degree + dissipation. With the default
        # dissipation=1 an interior grid node (out-degree 4) has threshold 5, a corner
        # (out-degree 2) has threshold 3.
        cfg = sp.canonical_config(grid(4))
        idx = cfg["index"]
        assert cfg["dissipation"] == 1
        assert cfg["capacity"][idx["1,1"]] == 5  # interior: 4 + 1
        assert cfg["capacity"][idx["0,0"]] == 3  # corner:   2 + 1

    def test_conservative_threshold_is_out_degree(self):
        # dissipation=0 → perfectly conservative → threshold == out-degree (classic BTW bulk).
        cfg = sp.canonical_config(grid(4), dissipation=0)
        idx = cfg["index"]
        assert cfg["capacity"][idx["1,1"]] == 4
        assert cfg["capacity"][idx["0,0"]] == 2

    def test_explicit_capacity_and_alias(self):
        c_cap = sp.canonical_config([[0, 1], [1, 0]], capacities={0: 3})
        c_thr = sp.canonical_config([[0, 1], [1, 0]], thresholds={0: 3})
        assert c_cap["commitment"] == c_thr["commitment"]
        assert c_cap["capacity"][c_cap["index"]["0"]] == 3

    def test_bad_capacity_rejected(self):
        with pytest.raises(ValueError):
            sp.canonical_config([[0, 1]], capacities={0: 0})


# --------------------------------------------------------------------------- #
# The abelian property — the load-bearing theorem this oracle's proof rests on #
# --------------------------------------------------------------------------- #

class TestAbelianOrderIndependence:
    def _relax(self, cfg, base_load, order_seed):
        load = base_load[:]
        topples = [0] * cfg["n"]
        budget = [sp.MAX_TOPPLES]
        unstable = [
            i for i in range(cfg["n"])
            if load[i] >= cfg["capacity"][i] and not cfg["is_sink"][i]
        ]
        random.Random(order_seed).shuffle(unstable)
        size = sp._stabilise(
            load, cfg["out"], cfg["capacity"], cfg["is_sink"], cfg["leaky"],
            unstable, topples, budget,
        )
        return size, tuple(topples), tuple(load)

    def test_relaxation_is_order_independent(self):
        # Dhar's theorem: the stable configuration AND per-site topple counts do not depend
        # on the order in which unstable sites are relaxed. This is the property the verifier
        # exploits — so we assert it directly with three different pop orders.
        cfg = sp.canonical_config(grid(6))
        # Drive every site well over threshold so a large avalanche is forced.
        base_load = [cfg["capacity"][i] + 3 for i in range(cfg["n"])]
        a = self._relax(cfg, base_load, 0)
        b = self._relax(cfg, base_load, 1)
        c = self._relax(cfg, base_load, 12345)
        assert a[0] == b[0] == c[0]      # same avalanche size
        assert a[1] == b[1] == c[1]      # same per-site topple counts
        assert a[2] == b[2] == c[2]      # same final stable configuration
        assert a[0] > 0

    def test_chain_dissipates_at_open_end(self):
        # In a path 0->1->...->N-1 the terminal node has no out-edge → it dissipates.
        # The whole pile must stabilise (no infinite avalanche).
        out = sp.cascade(chain(20), grains=1000, nonce="c")
        assert out["topple_total"] >= 0
        assert out["max_avalanche"] < 10_000  # finite

    def test_trapped_scc_still_terminates(self):
        # Two mutually-linked nodes with NO path to a boundary would topple forever under
        # naive BTW; the leaky-boundary treatment must make it stabilise.
        out = sp.cascade([[0, 1], [1, 0]], grains=500, nonce="t")
        assert out["topple_total"] >= 0
        assert "leaky" not in out  # internal detail not leaked, but it didn't hang


# --------------------------------------------------------------------------- #
# Power-law statistics                                                        #
# --------------------------------------------------------------------------- #

class TestPowerLaw:
    def test_grid_is_heavy_tailed(self):
        # A critical 2D sandpile produces a heavy-tailed avalanche distribution: a small
        # power-law exponent (tau well below ~3) and a max avalanche far above the mean.
        out = sp.cascade(grid(8), grains=4000, nonce="soc")
        assert 1.0 < out["tau"] < 3.0
        assert out["max_avalanche"] > 5 * out["mean_avalanche"]
        assert out["n_avalanches"] > 0

    def test_distribution_sorted_and_nonzero(self):
        out = sp.cascade(grid(7), grains=3000, nonce="d")
        dist = out["distribution"]
        sizes = [p["size"] for p in dist]
        assert sizes == sorted(sizes)
        assert all(p["size"] >= 1 and p["count"] >= 1 for p in dist)
        # The histogram counts must equal the number of non-zero avalanches.
        assert sum(p["count"] for p in dist) == out["n_avalanches"]

    def test_mle_tau_recovers_a_synthetic_power_law(self):
        # Draw from a genuine *discrete* power law P(s) ∝ s^(-alpha) by inverse-CDF
        # sampling, then check the MLE recovers the exponent. The discrete Clauset MLE uses
        # the continuous (s_min - 0.5) correction, which is most accurate for s_min >= 2, so
        # we fit there.
        import bisect

        alpha = 2.5
        s_max = 5000
        weights = [k ** (-alpha) for k in range(1, s_max + 1)]
        total = sum(weights)
        cdf, acc = [], 0.0
        for w in weights:
            acc += w
            cdf.append(acc / total)
        rng = random.Random(7)
        data = [bisect.bisect_left(cdf, rng.random()) + 1 for _ in range(40000)]
        tau = sp.mle_tau(data, s_min=2)
        assert abs(tau - alpha) < 0.25

    def test_mle_tau_monotone_in_steepness(self):
        # A steeper true exponent must yield a larger fitted tau — the estimator orders
        # heavy-tailed (small tau) below light-tailed (large tau).
        import bisect

        def draw(alpha, n=30000, s_max=5000, seed=3):
            weights = [k ** (-alpha) for k in range(1, s_max + 1)]
            total = sum(weights)
            cdf, acc = [], 0.0
            for w in weights:
                acc += w
                cdf.append(acc / total)
            rng = random.Random(seed)
            return [bisect.bisect_left(cdf, rng.random()) + 1 for _ in range(n)]

        tau_heavy = sp.mle_tau(draw(2.0), s_min=2)
        tau_light = sp.mle_tau(draw(3.0), s_min=2)
        assert tau_heavy < tau_light

    def test_tail_risk_monotone(self):
        out = sp.cascade(grid(8), grains=4000, nonce="tail")
        # 99% VaR/CVaR must be at least as large as 95% — deeper into the tail is worse.
        assert out["var99"]["var"] >= out["var95"]["var"]
        assert out["cvar99"] >= out["cvar95"]
        # CVaR (expected shortfall) is the mean *beyond* VaR, so it dominates VaR.
        assert out["cvar95"] >= out["var95"]["var"]

    def test_ks_is_a_fraction(self):
        out = sp.cascade(grid(7), grains=3000, nonce="ks")
        assert 0.0 <= out["ks"] <= 1.0


# --------------------------------------------------------------------------- #
# Triggers — the actionable systemic-risk output                              #
# --------------------------------------------------------------------------- #

class TestTriggers:
    def test_bridge_node_is_a_top_trigger(self):
        # The single bridge node H couples two clusters; it should rank among the nodes
        # that most often ignite cascades.
        out = sp.cascade(two_clusters_bridge(), grains=3000, nonce="bridge")
        trig_nodes = [t["node"] for t in out["triggers"]]
        assert "H" in trig_nodes
        assert out["triggers"][0]["avalanches_seeded"] > 0


# --------------------------------------------------------------------------- #
# Determinism + verification                                                  #
# --------------------------------------------------------------------------- #

class TestDeterminism:
    def test_same_input_same_output(self):
        a = sp.cascade(grid(7), grains=3000, nonce="rep")
        b = sp.cascade(grid(7), grains=3000, nonce="rep")
        assert a["config_commitment"] == b["config_commitment"]
        assert a["seed"] == b["seed"]
        assert a["topple_total"] == b["topple_total"]
        assert a["tau"] == b["tau"]
        assert a["distribution"] == b["distribution"]

    def test_seed_is_committed_to_nonce(self):
        a = sp.cascade(grid(6), grains=1500, nonce="aaa")
        b = sp.cascade(grid(6), grains=1500, nonce="bbb")
        assert a["seed"] != b["seed"]                       # nonce changes the schedule
        assert a["config_commitment"] == b["config_commitment"]  # but not the config


class TestVerify:
    def test_roundtrip_valid_both_claims(self):
        out = sp.cascade(grid(7), grains=3000, nonce="v")
        v = sp.verify(
            grid(7), grains=3000, nonce="v",
            claimed_tau=out["tau"], claimed_topple_total=out["topple_total"],
        )
        assert v["valid"] is True
        assert v["config_commitment"] == out["config_commitment"]
        assert v["recomputed_topple_total"] == out["topple_total"]
        assert v["recomputed_tau"] == out["tau"]

    def test_tampered_topple_total_rejected(self):
        out = sp.cascade(grid(7), grains=3000, nonce="v")
        v = sp.verify(
            grid(7), grains=3000, nonce="v",
            claimed_topple_total=out["topple_total"] + 1,
        )
        assert v["valid"] is False

    def test_tampered_tau_rejected(self):
        out = sp.cascade(grid(7), grains=3000, nonce="v")
        v = sp.verify(grid(7), grains=3000, nonce="v", claimed_tau=out["tau"] + 0.5)
        assert v["valid"] is False

    def test_verify_via_seed_matches_nonce_path(self):
        out = sp.cascade(grid(6), grains=2000, nonce="seedpath")
        v = sp.verify(
            grid(6), grains=2000, seed=out["seed"],
            claimed_tau=out["tau"], claimed_topple_total=out["topple_total"],
        )
        assert v["valid"] is True
        assert v["seed"] == out["seed"]

    def test_nothing_claimed_is_not_valid(self):
        # Proving nothing proves nothing — valid must be False with no claim supplied.
        v = sp.verify(grid(6), grains=500, nonce="x")
        assert v["valid"] is False
        assert v["recomputed_topple_total"] >= 0

    def test_wrong_graph_changes_commitment(self):
        out = sp.cascade(grid(6), grains=2000, nonce="g")
        v = sp.verify(
            grid(7), grains=2000, nonce="g",  # different graph
            claimed_topple_total=out["topple_total"],
        )
        assert v["config_commitment"] != out["config_commitment"]
        assert v["valid"] is False


# --------------------------------------------------------------------------- #
# Bounds / safety                                                             #
# --------------------------------------------------------------------------- #

class TestBounds:
    def test_grains_capped(self):
        out = sp.cascade(grid(5), grains=10 ** 9, nonce="cap")
        assert out["grains"] == sp.MAX_GRAINS

    def test_all_sink_rejected(self):
        with pytest.raises(ValueError):
            sp.cascade([["x", "y"]], sinks=["x", "y"], grains=100)


# --------------------------------------------------------------------------- #
# ASGI surface (oracle-core)                                                  #
# --------------------------------------------------------------------------- #

class TestApp:
    async def test_invoke_cascade(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://t") as client:
            r = await client.post(
                "/ai-market/v2/invoke",
                json={
                    "capability_id": "ablation.cascade@v1",
                    "input": {"edges": grid(7), "grains": 2500, "nonce": "asgi"},
                },
            )
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True
        out = body["output"]
        assert "config_commitment" in out
        assert 1.0 < out["tau"] < 3.0
        assert out["topple_total"] > 0
        assert body["receipt"]  # signed envelope present
        assert body["provenance"]["input_hash"]

    async def test_invoke_verify_roundtrip(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://t") as client:
            c = await client.post(
                "/ai-market/v2/invoke",
                json={
                    "capability_id": "ablation.cascade@v1",
                    "input": {"edges": grid(6), "grains": 2000, "nonce": "rt"},
                },
            )
            out = c.json()["output"]
            v = await client.post(
                "/ai-market/v2/invoke",
                json={
                    "capability_id": "ablation.verify@v1",
                    "input": {
                        "edges": grid(6), "grains": 2000, "nonce": "rt",
                        "claimed_tau": out["tau"],
                        "claimed_topple_total": out["topple_total"],
                    },
                },
            )
        vbody = v.json()
        assert vbody["ok"] is True
        assert vbody["output"]["valid"] is True

    async def test_invoke_missing_edges_is_error(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://t") as client:
            r = await client.post(
                "/ai-market/v2/invoke",
                json={"capability_id": "ablation.cascade@v1", "input": {}},
            )
        body = r.json()
        assert body["ok"] is False
        assert "edges" in body["error"]

    async def test_manifest_lists_capabilities(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://t") as client:
            r = await client.get("/ai-market/v2/manifest")
        ids = {t["capability_id"] for t in r.json()["tools"]}
        assert ids == {"ablation.cascade@v1", "ablation.verify@v1"}

    async def test_well_known(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://t") as client:
            r = await client.get("/.well-known/ai-market.json")
        body = r.json()
        assert body["ecosystem"]["product"] == "prod-ablation"
        assert body["capabilities_count"] == 2
