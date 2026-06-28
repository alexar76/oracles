"""Percola oracle spec — percolation-threshold network-resilience capabilities."""

from __future__ import annotations

import os
from typing import Any

from oracle_core import Capability, OracleSpec

from percola import percolation


def _threshold(d: dict[str, Any]) -> dict[str, Any]:
    edges = d.get("edges")
    if edges is None:
        raise ValueError("missing 'edges'")
    return percolation.analyze(
        nodes=d.get("nodes"),
        edges=edges,
        samples=int(d.get("samples", 50)),
        nonce=str(d.get("nonce", "0")),
        attack=str(d.get("attack", "both")),
    )


def _verify(d: dict[str, Any]) -> dict[str, Any]:
    edges = d.get("edges")
    if edges is None:
        raise ValueError("missing 'edges'")
    return percolation.verify(
        nodes=d.get("nodes"),
        edges=edges,
        attack=str(d.get("attack", "targeted")),
        f_c=d.get("f_c"),
        nonce=str(d.get("nonce", "0")),
        seed=(str(d["seed"]) if d.get("seed") is not None else None),
        samples=int(d.get("samples", 50)),
    )


_GRAPH_SCHEMA = {
    "nodes": {
        "type": "array",
        "description": "Optional explicit node labels (isolated nodes that have no edges).",
        "items": {"type": ["string", "integer"]},
    },
    "edges": {
        "type": "array",
        "description": "Undirected edges as [u, v] label pairs (directed input is symmetrised).",
        "items": {"type": "array", "minItems": 2, "maxItems": 2, "items": {"type": ["string", "integer"]}},
    },
    "samples": {"type": "integer", "minimum": 2, "maximum": percolation.MAX_SAMPLES, "default": 50,
                "description": "Resolution of the collapse curve (number of f samples)."},
}

_CURVE_SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "f": {"type": "number"}, "p_inf": {"type": "number"},
            "s2": {"type": "number"}, "removed": {"type": "integer"},
        },
    },
}


SPEC = OracleSpec(
    name="Percola Network-Resilience Oracle",
    product_id="prod-percola",
    description=(
        "Percolation-threshold analysis of trust/dependency graphs. Computes the "
        "critical attack fraction f_c at which the giant connected component "
        "collapses (a second-order connectivity phase transition), the full P_inf(f) "
        "collapse curve, the susceptibility (second-cluster) peak that witnesses the "
        "transition, and the ranked keystone set. Deterministic and replayable: every "
        "result is reproducible bit-for-bit from a committed graph — the threshold is "
        "proven by recomputation, not asserted."
    ),
    public_url=os.environ.get("PERCOLA_PUBLIC_URL", "http://localhost:9306"),
    categories=["network-resilience", "percolation", "phase-transition", "risk", "agent-tooling"],
    signing_key_path=os.environ.get("PERCOLA_SIGNING_KEY", "data/percola_signing_key"),
    related=["https://github.com/alexar76"],
    capabilities=[
        Capability(
            capability_id="percola.threshold@v1",
            product_id="prod-percola",
            description=(
                "Analyse a graph's connectivity resilience. Removes high-leverage nodes "
                "(deterministic greedy 'targeted' order) and a committed-seed 'random' "
                "baseline, tracking the giant component P_inf and second cluster S2. "
                "Returns f_c (critical attack fraction) for each attack, the collapse "
                "curves, a 0..1 robustness scalar (area under targeted P_inf), the "
                "keystone node set, and a graph_commitment for trustless replay."
            ),
            handler=_threshold,
            input_schema={
                "type": "object",
                "required": ["edges"],
                "properties": {
                    **_GRAPH_SCHEMA,
                    "attack": {"type": "string", "enum": ["targeted", "random", "both"], "default": "both"},
                    "nonce": {"type": ["string", "integer"], "default": "0",
                              "description": "Commit-reveal nonce for the random-attack baseline seed."},
                },
            },
            output_schema={
                "type": "object",
                "required": ["n", "m", "graph_commitment"],
                "properties": {
                    "n": {"type": "integer"}, "m": {"type": "integer"},
                    "graph_commitment": {"type": "string"},
                    "robustness": {"type": "number"},
                    "samples": {"type": "integer"},
                    "targeted": {
                        "type": "object",
                        "properties": {
                            "f_c": {"type": "number"}, "curve": _CURVE_SCHEMA,
                            "keystones": {"type": "array", "items": {"type": "string"}},
                            "order_hash": {"type": "string"},
                        },
                    },
                    "random": {
                        "type": "object",
                        "properties": {
                            "f_c": {"type": "number"}, "curve": _CURVE_SCHEMA,
                            "seed": {"type": "string"}, "nonce": {"type": "string"},
                            "order_hash": {"type": "string"},
                        },
                    },
                },
            },
            price_per_call_usd=0.01,
            p50_latency_ms=60,
            success_rate_30d=0.999,
        ),
        Capability(
            capability_id="percola.verify@v1",
            product_id="prod-percola",
            description=(
                "Trustless verification: re-derive the canonical graph, reconstruct the "
                "removal order (greedy for targeted; seed for random), replay the "
                "union-find sweep, and check the claimed f_c against the recomputed "
                "value. Cheap; needs no trust in the oracle."
            ),
            handler=_verify,
            input_schema={
                "type": "object",
                "required": ["edges", "f_c"],
                "properties": {
                    **_GRAPH_SCHEMA,
                    "attack": {"type": "string", "enum": ["targeted", "random"], "default": "targeted"},
                    "f_c": {"type": "number", "description": "Claimed critical attack fraction to check."},
                    "nonce": {"type": ["string", "integer"], "default": "0"},
                    "seed": {"type": "string", "description": "16-hex random-attack seed (alternative to nonce)."},
                },
            },
            output_schema={
                "type": "object",
                "required": ["valid", "graph_commitment", "recomputed_f_c"],
                "properties": {
                    "valid": {"type": "boolean"},
                    "attack": {"type": "string"},
                    "graph_commitment": {"type": "string"},
                    "recomputed_f_c": {"type": "number"},
                    "claimed_f_c": {"type": "number"},
                    "order_hash": {"type": "string"},
                    "seed": {"type": "string"},
                },
            },
            price_per_call_usd=0.001,
            p50_latency_ms=20,
            success_rate_30d=0.999,
        ),
    ],
)
