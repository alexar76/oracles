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
