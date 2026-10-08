import math

import numpy as np
import pytest
from httpx import ASGITransport, AsyncClient

from betti import homology as hl
from betti.main import app


# ---- crafted shapes with KNOWN topology (deterministic: fixed / seeded) -----

def circle(n=24, r=1.0):
    """n points evenly on a ring → exactly one loop (b1=1), one component (b0=1)."""
    return [[r * math.cos(2 * math.pi * k / n), r * math.sin(2 * math.pi * k / n)] for k in range(n)]


def two_clusters(gap=10.0, n=8):
    """Two tight blobs separated by a wide gap → b0=2 at small scale, 1 when merged."""
    rng = np.random.default_rng(1234)
    a = rng.normal(0.0, 0.15, size=(n, 2))
    b = rng.normal(0.0, 0.15, size=(n, 2)) + np.array([gap, 0.0])
    return np.vstack([a, b]).tolist()


def blob(n=30):
    """A filled disc of jittered points → no loops (b1=0): every cycle fills in."""
    rng = np.random.default_rng(7)
    pts = []
    while len(pts) < n:
        x, y = rng.uniform(-1, 1, size=2)
        if x * x + y * y <= 1.0:
            pts.append([float(x), float(y)])
    return pts


# =============================================================================
#  Topology: the homology algorithm on shapes whose answer we know
# =============================================================================

class TestKnownTopology:
    def test_circle_has_one_loop(self):
        pts = circle(n=24, r=1.0)
        # edge length between adjacent ring points ≈ 2*sin(pi/24) ≈ 0.261; a scale
        # comfortably above that (but below the diameter) connects the ring without
        # filling the hole → exactly one 1-cycle.
        out = hl.homology(pts, max_scale=0.5, max_dim=2, num_steps=20)
        assert out["betti"]["b0"] == 1, out["betti"]
        assert out["betti"]["b1"] == 1, out["betti"]
        assert out["betti"]["b2"] == 0
        # the loop is also present as a finite bar in dimension 1
        assert len(out["diagram"]["1"]) >= 1

    def test_two_clusters_merge_with_scale(self):
        pts = two_clusters(gap=10.0, n=8)
        small = hl.homology(pts, max_scale=1.0, max_dim=1, num_steps=10)
        assert small["betti"]["b0"] == 2, small["betti"]
        large = hl.homology(pts, max_scale=12.0, max_dim=1, num_steps=10)
        assert large["betti"]["b0"] == 1, large["betti"]
        # union-find cross-check agrees with the matrix-derived b0
        assert small["b0_unionfind"] == 2
        assert large["b0_unionfind"] == 1

    def test_blob_has_no_loops(self):
        pts = blob(n=30)
        # at half-diameter the disc is fully triangulated → no persistent 1-cycle
        out = hl.homology(pts, max_dim=2, num_steps=10)
        assert out["betti"]["b1"] == 0, out["betti"]
        assert out["betti"]["b0"] == 1

    def test_betti_curve_is_monotone_b0(self):
        # b0 can only decrease as the scale grows (components merge, never split).
        # Window must exceed the 10-unit gap so the two clusters actually merge.
        out = hl.homology(two_clusters(gap=10.0, n=8), max_scale=12.0, max_dim=1, num_steps=30)
        b0s = [row["b0"] for row in out["betti_curve"]]
        assert all(b0s[i] >= b0s[i + 1] for i in range(len(b0s) - 1)), b0s
        # at scale 0 every point is isolated (16 points); merges to a single blob.
        assert b0s[0] == 16 and b0s[-1] == 1


# =============================================================================
#  Bottleneck distance: a topology-drift metric
# =============================================================================

class TestBottleneck:
    def test_identical_clouds_distance_zero(self):
        pts = circle(n=20)
        out = hl.distance(pts, pts, dim=1, max_scale=1.0)
        assert out["bottleneck"] == pytest.approx(0.0, abs=1e-9)

    def test_circle_vs_blob_clearly_positive(self):
        c = circle(n=24, r=1.0)
        b = blob(n=30)
        out = hl.distance(c, b, dim=1, max_scale=1.0)
        # the circle has a long-lived loop; the blob has none → diagrams differ a lot
        assert out["bottleneck"] > 0.1, out

    def test_two_circles_close(self):
        # same shape, slightly different radius → small but defined drift
        c1 = circle(n=24, r=1.0)
        c2 = circle(n=24, r=1.05)
        out = hl.distance(c1, c2, dim=1, max_scale=1.0)
        assert out["bottleneck"] < 0.2, out


# =============================================================================
#  Hard caps (protocol does not validate input — handler must)
# =============================================================================

class TestCapsAndValidation:
    def test_missing_points_raises(self):
        with pytest.raises(ValueError):
            hl.homology(None)

    def test_malformed_points_raise(self):
        with pytest.raises(ValueError):
            hl.homology([1, 2, 3])  # not n×d

    def test_point_cap_reported_not_silent(self):
        rng = np.random.default_rng(0)
        many = rng.normal(size=(hl.MAX_POINTS + 50, 2)).tolist()
        out = hl.homology(many, max_scale=0.3, max_dim=1, num_steps=5)
        assert out["n"] == hl.MAX_POINTS
        assert any("point cap" in note for note in out["notes"]), out["notes"]


# =============================================================================
#  Async invoke + manifest (both capabilities, signed)
# =============================================================================

class TestBettiApp:
    @pytest.mark.asyncio
    async def test_invoke_homology(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://t") as c:
            r = await c.post(
                "/ai-market/v2/invoke",
                json={"capability_id": "betti.homology@v1",
                      "input": {"points": circle(n=24, r=1.0), "max_scale": 0.5, "max_dim": 2}},
            )
        body = r.json()
        assert body["ok"] is True
        out = body["output"]
        assert out["betti"]["b1"] == 1 and out["betti"]["b0"] == 1
        assert body["receipt"]  # signed envelope present

    @pytest.mark.asyncio
    async def test_invoke_distance(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://t") as c:
            r = await c.post(
                "/ai-market/v2/invoke",
                json={"capability_id": "betti.distance@v1",
                      "input": {"points_a": circle(n=20), "points_b": circle(n=20),
                                "dim": 1, "max_scale": 1.0}},
            )
        body = r.json()
        assert body["ok"] is True
        assert body["output"]["bottleneck"] == pytest.approx(0.0, abs=1e-9)

    @pytest.mark.asyncio
    async def test_invoke_bad_input_returns_error(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://t") as c:
            r = await c.post(
                "/ai-market/v2/invoke",
                json={"capability_id": "betti.homology@v1", "input": {}},
            )
        body = r.json()
        assert body["ok"] is False
        assert "points" in body["error"]

    @pytest.mark.asyncio
    async def test_manifest_signed(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://t") as c:
            m = (await c.get("/ai-market/v2/manifest")).json()
        ids = {t["capability_id"] for t in m["tools"]}
        assert ids == {"betti.homology@v1", "betti.distance@v1"}
        assert app.state.protocol.signer.verify_manifest_signature(m) is True


# --- 2026-09 re-audit: the two capabilities that sell computation must ration it ------
#
# betti.homology@v1 and betti.distance@v1 were the only capabilities in the family that
# scale with caller-supplied size while declaring none of oracle_core's four cost controls.
# Measured on the reference box, the declared 300-point ceiling is ~18 CPU-seconds for a
# homology and ~37 for a distance — one unauthenticated ~20 KB request — against a generic
# per-IP limiter that admits 120 invokes a minute.

import pytest

from betti import homology
from betti.capabilities import SPEC


def _cap(cap_id):
    return next(c for c in SPEC.capabilities if c.capability_id == cap_id)


@pytest.mark.parametrize("cap_id", ["betti.homology@v1", "betti.distance@v1"])
def test_the_heavy_capabilities_declare_every_cost_control(cap_id):
    cap = _cap(cap_id)
    assert cap.cost_ms is not None, "no cost estimate: the budget cannot ration what it cannot price"
    assert cap.cpu_budget_ms_per_min, "no per-caller CPU budget"
    assert cap.global_cpu_budget_ms_per_min, "no global CPU budget"
    assert cap.free_tier_max, "no free-tier ceiling"


@pytest.mark.parametrize("cap_id,field", [
    ("betti.homology@v1", "points"),
    ("betti.distance@v1", "points_a"),
])
def test_cost_grows_with_the_cloud_and_is_clamped_at_max_points(cap_id, field):
    cap = _cap(cap_id)

    def cost(n):
        return cap.estimate_cost_ms({
            "points": [[0.0, 0.0]] * n,
            "points_a": [[0.0, 0.0]] * n,
            "points_b": [[0.0, 0.0]] * n,
        })

    assert cost(40) < cost(80) < cost(150) < cost(300)
    # Past the hard cap the handler does no more work, so neither may the estimate grow.
    assert cost(homology.MAX_POINTS) == cost(homology.MAX_POINTS * 10)
    # And the biggest legal request must be expensive enough to actually exhaust a budget.
    assert cost(homology.MAX_POINTS) > 10_000


@pytest.mark.parametrize("cap_id", ["betti.homology@v1", "betti.distance@v1"])
def test_one_max_size_call_does_not_fit_twice_in_a_callers_budget(cap_id):
    """The point of the budget: the expensive tail is capped, not merely priced."""
    cap = _cap(cap_id)
    worst = cap.estimate_cost_ms({
        "points": [[0.0, 0.0]] * homology.MAX_POINTS,
        "points_a": [[0.0, 0.0]] * homology.MAX_POINTS,
        "points_b": [[0.0, 0.0]] * homology.MAX_POINTS,
    })
    # Two bounds, and both matter. The declared input ceiling must remain REACHABLE — a
    # budget that refuses the largest legal input turns the published schema into a lie —
    # while the budget must still admit only a handful of such calls per minute. At most
    # two: with the global 60 s/min ceiling that is about one core, which is the figure
    # oracle_core.tiers uses for the whole family's shared box.
    assert worst <= cap.cpu_budget_ms_per_min, "the largest legal input is unusable entirely"
    assert cap.cpu_budget_ms_per_min < 3 * worst, (
        f"{cap.capability_id}: budget {cap.cpu_budget_ms_per_min} admits "
        f"{cap.cpu_budget_ms_per_min / worst:.1f} max-size calls a minute — not a ration"
    )


def test_a_malformed_input_costs_the_floor_rather_than_raising():
    """A cost formula must never be the thing that takes the oracle down."""
    cap = _cap("betti.homology@v1")
    for bad in ({}, {"points": None}, {"points": "not a list"}, {"points": 5}):
        assert cap.estimate_cost_ms(bad) >= 1.0


def test_an_unpaid_over_size_cloud_is_refused_not_silently_clamped():
    from oracle_core.tiers import FreeTierExceeded, enforce_free_tier

    cap = _cap("betti.homology@v1")
    enforce_free_tier(cap.capability_id, cap.free_tier_max,
                      {"points": [[0.0, 0.0]] * cap.free_tier_max["points"]})
    with pytest.raises(FreeTierExceeded):
        enforce_free_tier(cap.capability_id, cap.free_tier_max,
                          {"points": [[0.0, 0.0]] * (cap.free_tier_max["points"] + 1)})


def test_the_free_tier_demo_size_is_actually_cheap():
    """A demo bound that still costs seconds would not be a bound."""
    cap = _cap("betti.distance@v1")
    n = cap.free_tier_max["points_a"]
    assert cap.estimate_cost_ms({
        "points_a": [[0.0, 0.0]] * n, "points_b": [[0.0, 0.0]] * n,
    }) < 1_000
