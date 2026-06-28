"""Lumen oracle spec — reputation / trust scoring (EigenTrust / PageRank) on oracle-core."""

from __future__ import annotations

import os
from typing import Any

from oracle_core import Capability, OracleSpec

from lumen import pagerank


def _reputation(d: dict[str, Any]) -> dict[str, Any]:
    return pagerank.run(d)


def _score(d: dict[str, Any]) -> dict[str, Any]:
    nodes = int(d["nodes"])
    target = int(d["target_node"])
    edges = d.get("edges", []) or []
    damping = float(d.get("damping", pagerank.DEFAULT_DAMPING))
    result = pagerank.pagerank(nodes, list(edges), damping=damping)
    scores = result["scores"]
    if not (0 <= target < nodes):
        raise ValueError(f"target_node out of range for n={nodes}")
    target_score = scores[target]
    rank = 1 + sum(1 for s in scores if s > target_score)
    percentile = ((nodes - rank + 1) / nodes) * 100.0 if nodes > 0 else 0.0
    return {
        "target_node": target,
        "score": target_score,
        "rank": rank,
        "of": nodes,
        "percentile": percentile,
    }


def _verify(d: dict[str, Any]) -> dict[str, Any]:
    nodes = int(d["nodes"])
    edges = d.get("edges", []) or []
    claimed = list(d["scores"])
    damping = float(d.get("damping", pagerank.DEFAULT_DAMPING))
    if len(claimed) != nodes:
        return {"valid": False, "error": f"scores length {len(claimed)} != nodes {nodes}"}
    result = pagerank.pagerank(nodes, list(edges), damping=damping)
    diffs = [abs(a - b) for a, b in zip(result["scores"], claimed)]
    max_diff = max(diffs) if diffs else 0.0
    return {"valid": max_diff < 1e-6, "max_abs_diff": max_diff}


SPEC = OracleSpec(
    name="Lumen Reputation Oracle",
    product_id="prod-lumen",
    description=(
        "Reputation / trust scoring for agent economies. Feed a directed weighted "
        "trust graph (who-trusts-whom) and Lumen returns EigenTrust / PageRank scores: "
        "the stationary distribution of a damped random walk over trust. Nodes trusted "
        "by trusted nodes shine brightest; sybil cliques cannot trap rank mass."
    ),
    public_url=os.environ.get("LUMEN_PUBLIC_URL", "http://localhost:9303"),
    categories=["reputation", "trust-scoring", "graph-analytics", "agent-tooling"],
    signing_key_path=os.environ.get("LUMEN_SIGNING_KEY", "data/lumen_signing_key"),
    related=["https://github.com/alexar76"],
    capabilities=[
        Capability(
            capability_id="lumen.reputation@v1",
            product_id="prod-lumen",
            description=(
                "Compute EigenTrust / PageRank reputation over a directed weighted trust "
                "graph. Builds a column-stochastic transition matrix with damping "
                "(default 0.85), power-iterates to the dominant eigenvector, and returns "
                "normalized scores (sum to 1), the iteration count, and convergence. "
                "Dangling nodes are handled via uniform teleport."
            ),
            handler=_reputation,
            input_schema={
                "type": "object",
                "required": ["nodes", "edges"],
                "properties": {
                    "nodes": {"type": "integer", "minimum": 1, "maximum": pagerank.MAX_NODES},
                    "edges": {
                        "type": "array",
                        "description": "Directed weighted trust edges [i, j, w]: i trusts j with weight w.",
                        "items": {
                            "type": "array",
                            "items": {"type": "number"},
                            "minItems": 3,
                            "maxItems": 3,
                        },
                    },
                    "damping": {"type": "number", "exclusiveMinimum": 0, "exclusiveMaximum": 1, "default": 0.85},
                },
            },
            output_schema={
                "type": "object",
                "required": ["scores", "iterations", "converged"],
                "properties": {
                    "scores": {"type": "array", "items": {"type": "number"}},
                    "iterations": {"type": "integer"},
                    "converged": {"type": "boolean"},
                },
            },
            price_per_call_usd=0.005,
            p50_latency_ms=20,
            success_rate_30d=0.999,
        ),
        Capability(
            capability_id="lumen.score@v1",
            product_id="prod-lumen",
            description=(
                "Single-agent trust lookup: PageRank score, rank, and percentile "
                "for one node in a directed weighted trust graph."
            ),
            handler=_score,
            input_schema={
                "type": "object",
                "required": ["nodes", "edges", "target_node"],
                "properties": {
                    "nodes": {"type": "integer", "minimum": 1, "maximum": pagerank.MAX_NODES},
                    "edges": {
                        "type": "array",
                        "items": {
                            "type": "array",
                            "items": {"type": "number"},
                            "minItems": 3,
                            "maxItems": 3,
                        },
                    },
                    "target_node": {"type": "integer", "minimum": 0},
                    "damping": {"type": "number", "exclusiveMinimum": 0, "exclusiveMaximum": 1, "default": 0.85},
                },
            },
            output_schema={
                "type": "object",
                "required": ["target_node", "score", "rank", "of", "percentile"],
                "properties": {
                    "target_node": {"type": "integer"},
                    "score": {"type": "number"},
                    "rank": {"type": "integer"},
                    "of": {"type": "integer"},
                    "percentile": {"type": "number"},
                },
            },
            price_per_call_usd=0.003,
            p50_latency_ms=20,
            success_rate_30d=0.999,
        ),
        Capability(
            capability_id="lumen.verify@v1",
            product_id="prod-lumen",
            description=(
                "Re-derive PageRank over the supplied graph and check claimed scores "
                "match the fixed point (trustless spot-check)."
            ),
            handler=_verify,
            input_schema={
                "type": "object",
                "required": ["nodes", "edges", "scores"],
                "properties": {
                    "nodes": {"type": "integer", "minimum": 1, "maximum": pagerank.MAX_NODES},
                    "edges": {
                        "type": "array",
                        "items": {
                            "type": "array",
                            "items": {"type": "number"},
                            "minItems": 3,
                            "maxItems": 3,
                        },
                    },
                    "scores": {"type": "array", "items": {"type": "number"}},
                    "damping": {"type": "number", "exclusiveMinimum": 0, "exclusiveMaximum": 1, "default": 0.85},
                    "graph_commitment": {"type": "string"},
                },
            },
            output_schema={
                "type": "object",
                "required": ["valid"],
                "properties": {
                    "valid": {"type": "boolean"},
                    "max_abs_diff": {"type": "number"},
                    "error": {"type": "string"},
                },
            },
            price_per_call_usd=0.002,
            p50_latency_ms=20,
            success_rate_30d=0.999,
        ),
    ],
)
