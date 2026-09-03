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
        ),
    ],
)
