"""Murmuration oracle spec — robust consensus aggregation on oracle-core."""

from __future__ import annotations

import os
from typing import Any

from oracle_core import Capability, OracleSpec

from murmuration import consensus


def _aggregate(d: dict[str, Any]) -> dict[str, Any]:
    values = d.get("values", [])
    trim = float(d.get("trim", 0.1))
    return consensus.aggregate(values, trim)


SPEC = OracleSpec(
    name="Murmuration Consensus Oracle",
    product_id="prod-murmuration",
    description=(
        "Robust consensus aggregation for agent swarms. Combines breakdown-resistant "
        "location estimators (median, trimmed mean, Tukey biweight M-estimator) with a "
        "DeGroot distributed-consensus simulation on a complete graph that provably "
        "converges to the mean. A single adversarial submission cannot move the result. "
        "Signed receipts — verifiable, no trust in the oracle."
    ),
    public_url=os.environ.get("MURMURATION_PUBLIC_URL", "http://localhost:9302"),
    categories=["consensus", "robust-statistics", "aggregation", "agent-tooling"],
    signing_key_path=os.environ.get("MURMURATION_SIGNING_KEY", "data/murmuration_signing_key"),
    related=["https://github.com/alexar76"],
    capabilities=[
        Capability(
            capability_id="murmuration.aggregate@v1",
            product_id="prod-murmuration",
            description=(
                "Aggregate a list of agent-submitted values into a single robust "
                "consensus number. Returns the median, symmetric trimmed mean, Tukey "
                "biweight location, and a DeGroot complete-graph consensus value with "
                "its iteration count. Outlier- and Byzantine-resistant."
            ),
            handler=_aggregate,
            input_schema={
                "type": "object",
                "required": ["values"],
                "properties": {
                    "values": {
                        "type": "array",
                        "items": {"type": "number"},
                        "minItems": 1,
                        "description": "Agent-submitted scalar estimates.",
                    },
                    "trim": {
                        "type": "number",
                        "minimum": 0.0,
                        "maximum": 0.499,
                        "default": 0.1,
                        "description": "Fraction trimmed from each tail for the trimmed mean.",
                    },
                },
            },
            output_schema={
                "type": "object",
                "required": [
                    "n",
                    "median",
                    "trimmed_mean",
                    "biweight",
                    "converged_value",
                    "iterations",
                ],
                "properties": {
                    "n": {"type": "integer"},
                    "median": {"type": "number"},
                    "trimmed_mean": {"type": "number"},
                    "biweight": {"type": "number"},
                    "converged_value": {"type": "number"},
                    "iterations": {"type": "integer"},
                },
            },
            price_per_call_usd=0.002,
            p50_latency_ms=8,
            success_rate_30d=0.999,
        ),
    ],
)
