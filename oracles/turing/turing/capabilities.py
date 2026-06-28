"""Turing oracle spec — blue-noise / structured sampling on oracle-core."""

from __future__ import annotations

import os
from typing import Any

from oracle_core import Capability, OracleSpec

from turing import bluenoise


def _bluenoise(d: dict[str, Any]) -> dict[str, Any]:
    seed = d.get("seed")
    return bluenoise.bluenoise(
        count=int(d.get("count", 256)),
        candidates=int(d.get("candidates", bluenoise.DEFAULT_CANDIDATES)),
        seed=None if seed is None else int(seed),
    )


SPEC = OracleSpec(
    name="Turing Blue-Noise Oracle",
    product_id="prod-turing",
    description=(
        "Structured sampling oracle. Generates blue-noise point sets in the unit "
        "square via Mitchell's best-candidate algorithm: points are spread evenly "
        "with a large minimum pairwise distance and no clumps — unlike uniform "
        "random. Deterministic from a seed, signed and verifiable on AIMarket v2."
    ),
    public_url=os.environ.get("TURING_PUBLIC_URL", "http://localhost:9305"),
    categories=["sampling", "blue-noise", "stippling", "monte-carlo", "agent-tooling"],
    signing_key_path=os.environ.get("TURING_SIGNING_KEY", "data/turing_signing_key"),
    related=["https://github.com/alexar76"],
    capabilities=[
        Capability(
            capability_id="turing.bluenoise@v1",
            product_id="prod-turing",
            description=(
                "Generate `count` blue-noise points in [0,1)^2 (Mitchell's "
                "best-candidate). Returns the points, count and the measured minimum "
                "pairwise distance. Pass `seed` for a reproducible set; omit it for a "
                "fresh os.urandom seed (reported back). `candidates` (default 10) "
                "trades cost for spacing quality."
            ),
            handler=_bluenoise,
            input_schema={
                "type": "object",
                "required": ["count"],
                "properties": {
                    "count": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": bluenoise.MAX_COUNT,
                        "description": "number of points to generate",
                    },
                    "candidates": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": bluenoise.MAX_CANDIDATES,
                        "default": bluenoise.DEFAULT_CANDIDATES,
                        "description": "random candidates considered per placement",
                    },
                    "seed": {
                        "type": "integer",
                        "description": "optional seed for a reproducible set",
                    },
                },
            },
            output_schema={
                "type": "object",
                "required": ["points", "count", "min_distance"],
                "properties": {
                    "points": {
                        "type": "array",
                        "items": {"type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 2},
                    },
                    "count": {"type": "integer"},
                    "min_distance": {"type": "number"},
                    "candidates": {"type": "integer"},
                    "seed": {"type": "integer"},
                    "seed_source": {"type": "string"},
                },
            },
            price_per_call_usd=0.002,
            p50_latency_ms=40,
            success_rate_30d=0.999,
        ),
    ],
)
