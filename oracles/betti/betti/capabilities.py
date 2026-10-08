"""Betti oracle spec — persistent-homology / topological-shape capabilities."""

from __future__ import annotations

import os
from typing import Any

from oracle_core import Capability, OracleSpec

from betti import homology


def _homology(d: dict[str, Any]) -> dict[str, Any]:
    # The protocol does NOT validate input_schema. The handler validates required
    # fields (raising ValueError -> {ok:false}) and the homology module hard-caps
    # the point count and total simplices (a Rips complex explodes) — clipping is
    # reported in the output `notes`/`capped` fields, never silent.
    return homology.homology(
        points_raw=d.get("points"),
        max_scale=d.get("max_scale"),
        max_dim=int(d.get("max_dim", 2)),
        num_steps=int(d.get("num_steps", 40)),
    )


def _distance(d: dict[str, Any]) -> dict[str, Any]:
    return homology.distance(
        points_a_raw=d.get("points_a"),
        points_b_raw=d.get("points_b"),
        dim=int(d.get("dim", 1)),
        max_scale=d.get("max_scale"),
    )


_POINTS_SCHEMA = {
    "type": "array",
    "description": "Point cloud as an n×d array of real coordinates (n capped at 300).",
    "items": {"type": "array", "items": {"type": "number"}},
}

_DIAGRAM_SCHEMA = {
    "type": "array",
    "description": "Persistence intervals [birth, death] (death may be 'inf' for essential bars).",
    "items": {"type": "array", "minItems": 2, "maxItems": 2, "items": {"type": "number"}},
}


#: Cost controls for the two capabilities that sell computation. Numbers measured on the
#: reference box (oracles/.venv, single core) against _homology/_distance; only RELATIVE
#: accuracy matters, since a faster machine scales every cost alike.
#:
#: 80 points is the demo size an unpaid caller gets: ~107 ms for a homology, ~450 ms for a
#: distance — large enough that the persistence diagram is fully visible and the topology
#: question really answered, small enough that a loop of them costs a fraction of a core.
_FREE_TIER_POINTS = 80
#: 3.7 is the measured exponent (3.6 ms at n=30, 15.1 at 45, 37.6 at 60, 107.3 at 80);
#: 80_000 the fitted constant, so cost ~= n**3.7 / 80_000 ms.
_COST_EXPONENT = 3.7
_COST_DIVISOR = 80_000.0
#: One estimate may not exceed a minute — past that the number stops rationing and starts
#: being a refusal in disguise.
_COST_CEILING_MS = 60_000.0
#: One max-size paid call per caller per minute, then refusal.
_CPU_BUDGET_MS_PER_MIN = 45_000.0
#: One core, summed over ALL callers — the figure oracle_core.tiers uses, and the whole
#: family shares one box. Per-IP limits are the wrong tool against a distributed caller.
_GLOBAL_CPU_BUDGET_MS_PER_MIN = 60_000.0


def _cloud_cost_ms(points: Any) -> float:
    """Expected CPU-ms for one point cloud, clamped to the hard MAX_POINTS cap.

    Declared, never measured: it must be known BEFORE the work is done in order to ration
    it. A non-list input costs the 1.0 floor — malformed input is the handler's problem,
    and a cost formula must never be able to take the oracle down.
    """
    try:
        n = len(points) if isinstance(points, (list, tuple)) else 0
    except TypeError:
        n = 0
    n = min(n, homology.MAX_POINTS)
    if n <= 0:
        return 1.0
    return min(_COST_CEILING_MS, (float(n) ** _COST_EXPONENT) / _COST_DIVISOR + 1.0)


SPEC = OracleSpec(
    name="Betti Topological-Shape Oracle",
    product_id="prod-betti",
    description=(
        "Persistent homology of a point cloud — the topological 'shape' of data. "
        "Builds a Vietoris-Rips filtration and runs the standard GF(2) boundary "
        "reduction to read off Betti numbers b0 (connected components), b1 "
        "(loops/holes) and b2 (voids/cavities) as a function of scale, plus the "
        "persistence barcode/diagram. A bottleneck distance between two diagrams is "
        "a basis-free, noise-stable drift detector: small = same shape, large = the "
        "topology changed. Useful for clustering structure, cycle/anomaly detection, "
        "manifold sanity-checks and shape-change alarms in agent data streams."
    ),
    public_url=os.environ.get("BETTI_PUBLIC_URL", "http://localhost:9313"),
    categories=["topology", "persistent-homology", "shape-analysis", "drift-detection", "agent-tooling"],
    signing_key_path=os.environ.get("BETTI_SIGNING_KEY", "data/betti_signing_key"),
    related=["https://github.com/alexar76"],
    capabilities=[
        Capability(
            capability_id="betti.homology@v1",
            product_id="prod-betti",
            description=(
                "Compute the persistent homology of a point cloud. Returns Betti "
                "numbers b0/b1/b2 at max_scale, the full Betti curve b_k(scale), and "
                "the persistence diagram per dimension. Scale defaults to half the "
                "cloud diameter; set max_dim=1 to skip voids (cheaper). Hard-capped "
                "at 300 points / 150k simplices — clipping is reported, never silent."
            ),
            handler=_homology,
            input_schema={
                "type": "object",
                "required": ["points"],
                "properties": {
                    "points": _POINTS_SCHEMA,
                    "max_scale": {"type": "number", "exclusiveMinimum": 0,
                                  "description": "Filtration ceiling; default = half the cloud diameter."},
                    "max_dim": {"type": "integer", "enum": [1, 2], "default": 2,
                                "description": "Top homology dimension (1 = b0,b1; 2 = also b2/voids)."},
                    "num_steps": {"type": "integer", "minimum": 2, "maximum": 200, "default": 40,
                                  "description": "Resolution of the Betti curve."},
                },
            },
            output_schema={
                "type": "object",
                "required": ["n", "d", "betti", "betti_curve", "diagram", "max_scale", "simplices_count", "capped"],
                "properties": {
                    "n": {"type": "integer"}, "d": {"type": "integer"},
                    "betti": {"type": "object", "properties": {
                        "b0": {"type": "integer"}, "b1": {"type": "integer"}, "b2": {"type": "integer"}}},
                    "betti_curve": {"type": "array", "items": {"type": "object", "properties": {
                        "scale": {"type": "number"}, "b0": {"type": "integer"},
                        "b1": {"type": "integer"}, "b2": {"type": "integer"}}}},
                    "diagram": {"type": "object", "properties": {
                        "0": _DIAGRAM_SCHEMA, "1": _DIAGRAM_SCHEMA, "2": _DIAGRAM_SCHEMA}},
                    "max_scale": {"type": "number"}, "max_dim": {"type": "integer"},
                    "simplices_count": {"type": "integer"},
                    "b0_unionfind": {"type": "integer"},
                    "capped": {"type": "boolean"},
                    "notes": {"type": "array", "items": {"type": "string"}},
                },
            },
            price_per_call_usd=0.008,
            p50_latency_ms=120,
            success_rate_30d=0.999,
            # Sells COMPUTATION, and declared none of the four cost controls until the
            # 2026-09 audit — the only capabilities in the family that scale with
            # caller-supplied size and ration nothing. oracle_core.tiers says these knobs
            # exist for work where "a single call pins a whole core for its whole duration";
            # measured, a Rips complex plus persistence reduction is ~n^3.7, which puts the
            # declared 300-point ceiling at ~18 CPU-SECONDS for one ~10 KB request — the
            # same order as aestus.seal, which that doc singles out. The generic per-IP
            # invoke limiter admits 120/min, so one address could lawfully demand far more
            # than the box has.
            free_tier_max={"points": _FREE_TIER_POINTS},
            cost_ms=lambda d: _cloud_cost_ms(d.get("points")),
            cpu_budget_ms_per_min=_CPU_BUDGET_MS_PER_MIN,
            global_cpu_budget_ms_per_min=_GLOBAL_CPU_BUDGET_MS_PER_MIN,
        ),
        Capability(
            capability_id="betti.distance@v1",
            product_id="prod-betti",
            description=(
                "Bottleneck distance between the persistence diagrams of two point "
                "clouds in one homology dimension (default b1/loops). The basis-free "
                "drift metric: ~0 when the two clouds share a topology, clearly "
                "positive when the shape changed (a loop appeared/vanished, components "
                "merged, a void opened). Exact matching on the capped diagrams."
            ),
            handler=_distance,
            input_schema={
                "type": "object",
                "required": ["points_a", "points_b"],
                "properties": {
                    "points_a": _POINTS_SCHEMA,
                    "points_b": _POINTS_SCHEMA,
                    "dim": {"type": "integer", "enum": [0, 1, 2], "default": 1,
                            "description": "Homology dimension to compare (0=components, 1=loops, 2=voids)."},
                    "max_scale": {"type": "number", "exclusiveMinimum": 0,
                                  "description": "Shared filtration ceiling; default = max half-diameter of the two."},
                },
            },
            output_schema={
                "type": "object",
                "required": ["dim", "bottleneck", "diagram_a", "diagram_b"],
                "properties": {
                    "dim": {"type": "integer"},
                    "bottleneck": {"type": "number"},
                    "max_scale": {"type": "number"},
                    "diagram_a": _DIAGRAM_SCHEMA,
                    "diagram_b": _DIAGRAM_SCHEMA,
                },
            },
            price_per_call_usd=0.004,
            p50_latency_ms=200,
            success_rate_30d=0.999,
            # Two clouds, two independent persistence computations, plus the exact
            # bottleneck matching between the resulting diagrams. Measured: 17 ms at 40
            # points per cloud, 100.5 at 60, 446.5 at 90 — the same ~n^3.7, so the estimate
            # is the sum of the two clouds with the matching absorbed into the constant. At
            # the declared 300+300 ceiling that is ~37 CPU-seconds for one ~20 KB request.
            free_tier_max={"points_a": _FREE_TIER_POINTS, "points_b": _FREE_TIER_POINTS},
            cost_ms=lambda d: min(
                _COST_CEILING_MS,
                _cloud_cost_ms(d.get("points_a")) + _cloud_cost_ms(d.get("points_b")),
            ),
            cpu_budget_ms_per_min=_CPU_BUDGET_MS_PER_MIN,
            global_cpu_budget_ms_per_min=_GLOBAL_CPU_BUDGET_MS_PER_MIN,
        ),
    ],
)
