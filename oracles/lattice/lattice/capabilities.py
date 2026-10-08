"""Lattice oracle spec — low-discrepancy (quasi-random) sequences on oracle-core."""

from __future__ import annotations

import os
from typing import Any

from oracle_core import Capability, OracleSpec

from lattice import halton


def _sequence(d: dict[str, Any]) -> dict[str, Any]:
    try:
        count = int(d.get("count", 256))
        dim = int(d.get("dim", 2))
        skip = int(d.get("skip", 0))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"malformed input: {exc}") from exc
    return halton.run(count, dim, skip)


SPEC = OracleSpec(
    name="Lattice Oracle",
    product_id="prod-lattice",
    description=(
        "Low-discrepancy (quasi-random) sequence oracle. Halton / van der Corput "
        "radical-inverse points fill the unit cube far more evenly than white noise "
        "(O((log N)^d / N) discrepancy vs O(1/sqrt(N))). Deterministic, reproducible, "
        "dependency-free — the substrate for quasi-Monte-Carlo integration, sampling, "
        "and space-filling search."
    ),
    public_url=os.environ.get("LATTICE_PUBLIC_URL", "http://localhost:9301"),
    categories=["quasi-random", "sampling", "monte-carlo", "agent-tooling"],
    signing_key_path=os.environ.get("LATTICE_SIGNING_KEY", "data/lattice_signing_key"),
    related=["https://github.com/alexar76"],
    capabilities=[
        Capability(
            capability_id="lattice.sequence@v1",
            product_id="prod-lattice",
            description=(
                "Generate `count` points of the `dim`-dimensional Halton "
                "low-discrepancy sequence in [0,1)^dim, using successive coprime "
                "prime bases. Quasi-random: fills space more evenly than RNG, so "
                "quasi-Monte-Carlo estimators converge faster. Deterministic for "
                "given (count, dim, skip)."
            ),
            handler=_sequence,
            input_schema={
                "type": "object",
                "properties": {
                    "count": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": halton.MAX_COUNT,
                        "default": 256,
                    },
                    "dim": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": halton.MAX_DIM,
                        "default": 2,
                    },
                    "skip": {"type": "integer", "minimum": 0, "default": 0},
                },
            },
            output_schema={
                "type": "object",
                "required": ["points", "dim", "count", "bases"],
                "properties": {
                    "sequence": {"type": "string"},
                    "points": {
                        "type": "array",
                        "items": {"type": "array", "items": {"type": "number"}},
                    },
                    "dim": {"type": "integer"},
                    "count": {"type": "integer"},
                    "skip": {"type": "integer"},
                    "bases": {"type": "array", "items": {"type": "integer"}},
                },
            },
            price_per_call_usd=0.002,
            p50_latency_ms=8,
            success_rate_30d=0.999,
        ),
    ],
)
