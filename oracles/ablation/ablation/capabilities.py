"""Ablation oracle spec — systemic cascade-risk (abelian sandpile / SOC) capabilities."""

from __future__ import annotations

import os
from typing import Any

from oracle_core import Capability, OracleSpec

from ablation import sandpile


def _cascade(d: dict[str, Any]) -> dict[str, Any]:
    edges = d.get("edges")
    if edges is None:
        raise ValueError("missing 'edges'")
    return sandpile.cascade(
        edges=edges,
        capacities=d.get("capacities"),
        thresholds=d.get("thresholds"),
        nodes=d.get("nodes"),
        sinks=d.get("sinks"),
        grains=int(d.get("grains", 4000)),
        nonce=str(d.get("nonce", "0")),
        s_min=int(d.get("s_min", 1)),
        dissipation=int(d.get("dissipation", 1)),
    )


def _verify(d: dict[str, Any]) -> dict[str, Any]:
    edges = d.get("edges")
    if edges is None:
        raise ValueError("missing 'edges'")
    return sandpile.verify(
        edges=edges,
        capacities=d.get("capacities"),
        thresholds=d.get("thresholds"),
        nodes=d.get("nodes"),
        sinks=d.get("sinks"),
        grains=int(d.get("grains", 4000)),
        nonce=str(d.get("nonce", "0")),
        seed=(str(d["seed"]) if d.get("seed") is not None else None),
        claimed_tau=d.get("claimed_tau"),
        claimed_topple_total=d.get("claimed_topple_total"),
        s_min=int(d.get("s_min", 1)),
        dissipation=int(d.get("dissipation", 1)),
    )


_GRAPH_SCHEMA = {
    "nodes": {
        "type": "array",
        "description": "Optional explicit node labels (e.g. isolated counterparties with no edges).",
        "items": {"type": ["string", "integer"]},
    },
    "edges": {
        "type": "array",
        "description": (
            "Directed exposure edges as [u, v] label pairs: stress flows u->v "
            "(u depends on / owes v, so u's distress lands on v)."
        ),
        "items": {"type": "array", "minItems": 2, "maxItems": 2, "items": {"type": ["string", "integer"]}},
    },
    "capacities": {
        "type": "object",
        "description": (
            "Optional per-node toppling threshold (capacity), label->int>=1. Defaults to the "
            "node's out-degree (canonical BTW rule)."
        ),
        "additionalProperties": {"type": "integer", "minimum": 1},
    },
    "thresholds": {
        "type": "object",
        "description": "Alias for 'capacities'.",
        "additionalProperties": {"type": "integer", "minimum": 1},
    },
    "sinks": {
        "type": "array",
        "description": "Optional sink nodes that dissipate grains and never topple (boundary).",
        "items": {"type": ["string", "integer"]},
    },
    "grains": {
        "type": "integer", "minimum": 1, "maximum": sandpile.MAX_GRAINS, "default": 4000,
        "description": "Number of unit stress grains to drive into the system.",
    },
    "nonce": {
        "type": ["string", "integer"], "default": "0",
        "description": "Commit-reveal nonce for the drive-schedule seed = H(config_commitment || nonce).",
    },
    "s_min": {
        "type": "integer", "minimum": 1, "default": 1,
        "description": "Lower cutoff for the power-law MLE fit (fit only avalanches of size >= s_min).",
    },
    "dissipation": {
        "type": "integer", "minimum": 0, "default": 1,
        "description": (
            "Grains leaked to the open boundary per topple (the system's leak rate). "
            ">=1 (default) guarantees criticality + termination on any graph; 0 = perfectly "
            "conservative (dissipation only at explicit sinks / dead-ends)."
        ),
    },
}

_DIST_SCHEMA = {
    "type": "array",
    "description": "Avalanche-size distribution as {size, count} pairs (log-log power-law support).",
    "items": {
        "type": "object",
        "properties": {"size": {"type": "integer"}, "count": {"type": "integer"}},
    },
}

_TAIL_SCHEMA = {
    "type": "object",
    "properties": {
        "var": {"type": "number"}, "cvar": {"type": "number"}, "quantile": {"type": "number"},
    },
}


SPEC = OracleSpec(
    name="Ablation Systemic Cascade-Risk Oracle",
    product_id="prod-ablation",
    description=(
        "Self-organized-criticality cascade-risk analysis of exposure / dependency graphs "
        "via the Bak-Tang-Wiesenfeld abelian sandpile. Drives unit stress into a "
        "driven-dissipative network and records the heavy-tailed distribution of avalanche "
        "(cascade) MAGNITUDES: the fitted power-law exponent tau (MLE) with a KS "
        "goodness-of-fit, the expected and tail (VaR/CVaR at 95% & 99%) avalanche size, and "
        "the trigger nodes that most often ignite large cascades. Deterministic and "
        "replayable: the abelian property makes per-site topple counts order-independent, so "
        "every result is reproducible bit-for-bit from a committed config — systemic risk "
        "proven by recomputation, not asserted."
    ),
    public_url=os.environ.get("ABLATION_PUBLIC_URL", "http://localhost:9308"),
    categories=["systemic-risk", "contagion", "self-organized-criticality", "sandpile", "risk", "agent-tooling"],
    signing_key_path=os.environ.get("ABLATION_SIGNING_KEY", "data/ablation_signing_key"),
    related=["https://github.com/alexar76"],
    capabilities=[
        Capability(
            capability_id="ablation.cascade@v1",
            product_id="prod-ablation",
            description=(
                "Analyse a network's systemic cascade risk. Treats the exposure graph as an "
                "abelian sandpile, drives `grains` unit shocks on a committed pseudo-random "
                "schedule, and stabilises after each via a topple queue. Returns the avalanche "
                "size distribution, the MLE power-law exponent tau + KS fit, the mean and tail "
                "(VaR/CVaR 95% & 99%) avalanche size, the top trigger nodes, a config_commitment "
                "and the committed seed for trustless replay. Small tau / heavy tail = one "
                "default ripples across the whole market."
            ),
            handler=_cascade,
            input_schema={
                "type": "object",
                "required": ["edges"],
                "properties": dict(_GRAPH_SCHEMA),
            },
            output_schema={
                "type": "object",
                "required": ["n", "m", "config_commitment", "tau", "topple_total"],
                "properties": {
                    "n": {"type": "integer"}, "m": {"type": "integer"},
                    "grains": {"type": "integer"},
                    "config_commitment": {"type": "string"},
                    "seed": {"type": "string"}, "nonce": {"type": "string"},
                    "dissipation": {"type": "integer"},
                    "topple_total": {"type": "integer"},
                    "n_avalanches": {"type": "integer"},
                    "distribution": _DIST_SCHEMA,
                    "tau": {"type": "number"}, "ks": {"type": "number"}, "s_min": {"type": "integer"},
                    "mean_avalanche": {"type": "number"}, "max_avalanche": {"type": "integer"},
                    "var95": _TAIL_SCHEMA, "cvar95": {"type": "number"},
                    "var99": _TAIL_SCHEMA, "cvar99": {"type": "number"},
                    "triggers": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "node": {"type": "string"},
                                "big_cascades": {"type": "integer"},
                                "avalanches_seeded": {"type": "integer"},
                                "total_cascade_mass": {"type": "integer"},
                            },
                        },
                    },
                },
            },
            price_per_call_usd=0.01,
            p50_latency_ms=90,
            success_rate_30d=0.999,
        ),
        Capability(
            capability_id="ablation.verify@v1",
            product_id="prod-ablation",
            description=(
                "Trustless verification: re-derive the canonical config, replay the "
                "driven-dissipative sandpile over the committed schedule (seed = "
                "H(config_commitment || nonce), or a supplied seed), recompute the "
                "order-independent topple total and power-law tau, and check them against the "
                "claimed values. The abelian theorem guarantees bit-for-bit reproduction "
                "regardless of relaxation order. Cheap; needs no trust in the oracle."
            ),
            handler=_verify,
            input_schema={
                "type": "object",
                "required": ["edges"],
                "properties": {
                    **_GRAPH_SCHEMA,
                    "seed": {"type": "string", "description": "16-hex drive seed (alternative to nonce)."},
                    "claimed_tau": {"type": "number", "description": "Claimed power-law exponent to check."},
                    "claimed_topple_total": {"type": "integer", "description": "Claimed total topple count to check."},
                },
            },
            output_schema={
                "type": "object",
                "required": ["valid", "config_commitment", "recomputed_topple_total", "recomputed_tau"],
                "properties": {
                    "valid": {"type": "boolean"},
                    "config_commitment": {"type": "string"},
                    "seed": {"type": "string"}, "nonce": {"type": ["string", "null"]},
                    "recomputed_topple_total": {"type": "integer"},
                    "recomputed_tau": {"type": "number"},
                    "claimed_topple_total": {"type": ["integer", "null"]},
                    "claimed_tau": {"type": ["number", "null"]},
                },
            },
            price_per_call_usd=0.001,
            p50_latency_ms=30,
            success_rate_30d=0.999,
        ),
    ],
)
