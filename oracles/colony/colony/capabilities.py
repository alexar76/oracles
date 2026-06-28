"""Colony oracle spec — combinatorial optimization with a quality certificate."""

from __future__ import annotations

import os
from typing import Any

from oracle_core import Capability, OracleSpec

from colony import tsp


def _optimize(d: dict[str, Any]) -> dict[str, Any]:
    points = d.get("points")
    if points is None:
        raise ValueError("missing 'points'")
    iterations = int(d.get("iterations", 1000))
    result = tsp.solve(points, iterations=iterations)
    # Public output contract (nn_length kept as a bonus diagnostic field).
    return {
        "tour": result["tour"],
        "length": result["length"],
        "lower_bound": result["lower_bound"],
        "gap": result["gap"],
        "n": result["n"],
        "nn_length": result["nn_length"],
    }


SPEC = OracleSpec(
    name="Colony Optimization Oracle",
    product_id="prod-colony",
    description=(
        "Combinatorial optimization with a quality certificate. Solves the Euclidean "
        "travelling-salesman problem with nearest-neighbour construction + 2-opt local "
        "search, and returns the tour together with a real admissible lower bound and "
        "the optimality gap — so an agent knows how close to optimal its route is."
    ),
    public_url=os.environ.get("COLONY_PUBLIC_URL", "http://localhost:9304"),
    categories=["combinatorial-optimization", "routing", "tsp", "agent-tooling"],
    signing_key_path=os.environ.get("COLONY_SIGNING_KEY", "data/colony_signing_key"),
    related=["https://github.com/alexar76"],
    capabilities=[
        Capability(
            capability_id="colony.optimize@v1",
            product_id="prod-colony",
            description=(
                "Optimize a tour over >=3 2D points: nearest-neighbour + 2-opt. Returns "
                "the tour (a permutation), its length, an admissible lower bound "
                "(sum of each node's cheapest incident edge / 2), and gap = "
                "(length - lower_bound) / lower_bound. The gap is a certificate of how "
                "far from optimal the tour can possibly be."
            ),
            handler=_optimize,
            input_schema={
                "type": "object",
                "required": ["points"],
                "properties": {
                    "points": {
                        "type": "array",
                        "minItems": 3,
                        "items": {
                            "type": "array",
                            "minItems": 2,
                            "maxItems": 2,
                            "items": {"type": "number"},
                        },
                        "description": "List of [x, y] coordinates (at least 3).",
                    },
                    "iterations": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": tsp.MAX_ITERATIONS,
                        "default": 1000,
                        "description": "2-opt improvement budget.",
                    },
                },
            },
            output_schema={
                "type": "object",
                "required": ["tour", "length", "lower_bound", "gap", "n"],
                "properties": {
                    "tour": {"type": "array", "items": {"type": "integer"}},
                    "length": {"type": "number"},
                    "lower_bound": {"type": "number"},
                    "gap": {"type": "number"},
                    "n": {"type": "integer"},
                    "nn_length": {"type": "number"},
                },
            },
            price_per_call_usd=0.005,
            p50_latency_ms=25,
            success_rate_30d=0.999,
        ),
    ],
)
