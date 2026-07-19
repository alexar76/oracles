"""Fermat oracle spec — least-time routing/composition with a dual optimality certificate."""

from __future__ import annotations

import os
from typing import Any

from oracle_core import Capability, OracleSpec

from fermat import eikonal


def _blend(d: dict[str, Any]) -> dict[str, float] | None:
    b = d.get("blend")
    if b is None:
        return None
    if not isinstance(b, dict):
        raise ValueError("'blend' must be an object of coefficients")
    return {k: float(v) for k, v in b.items()}


def _route(d: dict[str, Any]) -> dict[str, Any]:
    edges = d.get("edges")
    if edges is None:
        raise ValueError("missing 'edges'")
    if d.get("start") is None:
        raise ValueError("missing 'start'")
    if d.get("goal") is None:
        raise ValueError("missing 'goal'")
    return eikonal.route(
        nodes=d.get("nodes"),
        edges=edges,
        start=d["start"],
        goal=d["goal"],
        blend=_blend(d),
    )


def _verify(d: dict[str, Any]) -> dict[str, Any]:
    edges = d.get("edges")
    if edges is None:
        raise ValueError("missing 'edges'")
    if d.get("potentials") is None:
        raise ValueError("missing 'potentials' (the dual certificate T(v))")
    if d.get("start") is None or d.get("goal") is None:
        raise ValueError("missing 'start'/'goal'")
    return eikonal.verify(
        nodes=d.get("nodes"),
        edges=edges,
        path=d.get("path"),
        potentials=d["potentials"],
        start=d["start"],
        goal=d["goal"],
        total=d.get("total"),
        blend=_blend(d),
    )


_NODE = {"type": ["string", "integer"]}

_EDGES_SCHEMA = {
    "type": "array",
    "description": (
        "Directed weighted edges. Two shapes are accepted and may be mixed: "
        "(a) [u, v, weight] where weight is the already-blended non-negative refractive "
        "index n(u,v); or (b) {from,to, cost?, latency?, reputation?} where the index is "
        "derived as a*cost + b*(latency/scale) + c*(1-reputation) using 'blend'. A bare "
        "[u, v] is weight 0."
    ),
    "items": {
        "oneOf": [
            {"type": "array", "minItems": 2, "maxItems": 3},
            {
                "type": "object",
                "properties": {
                    "from": _NODE, "to": _NODE, "u": _NODE, "v": _NODE,
                    "source": _NODE, "target": _NODE,
                    "cost": {"type": "number", "minimum": 0},
                    "latency": {"type": "number", "minimum": 0},
                    "reputation": {"type": "number", "minimum": 0, "maximum": 1},
                    "weight": {"type": "number", "minimum": 0},
                    "n": {"type": "number", "minimum": 0},
                },
            },
        ]
    },
}

_BLEND_SCHEMA = {
    "type": "object",
    "description": (
        "Refractive-index blend coefficients for dict-shaped edges: "
        "{cost,latency,reputation,latency_scale}. Defaults {1,1,1,1000}."
    ),
    "properties": {
        "cost": {"type": "number"}, "latency": {"type": "number"},
        "reputation": {"type": "number"}, "latency_scale": {"type": "number"},
    },
}

_POTENTIALS_SCHEMA = {
    "type": "object",
    "description": "Eikonal potential T(v) = least cost-to-reach, keyed by node label (null = unreachable).",
    "additionalProperties": {"type": ["number", "null"]},
}


SPEC = OracleSpec(
    name="Fermat Least-Time Routing Oracle",
    product_id="prod-fermat",
    description=(
        "Provably-optimal routing and composition of capabilities over a weighted "
        "service graph, by Fermat's principle of least time. Each edge is a refractive "
        "index n(u,v) blending cost + latency + (1 - reputation); the least-'time' "
        "composition path start -> goal is the optical ray, computed with Dijkstra. "
        "Returns that path, its total, the eikonal potential T(v) for every node, and a "
        "DUAL / complementary-slackness certificate: a verifier checks feasibility "
        "T(v) <= T(u)+n(u,v) on every edge and tightness on every path edge in O(E) and "
        "thereby confirms GLOBAL optimality without re-running Dijkstra. Deterministic "
        "and replayable from a SHA-256 graph_commitment."
    ),
    public_url=os.environ.get("FERMAT_PUBLIC_URL", "http://localhost:9307"),
    categories=["routing", "composition", "optimization", "least-time", "agent-tooling"],
    signing_key_path=os.environ.get("FERMAT_SIGNING_KEY", "data/fermat_signing_key"),
    related=["https://github.com/alexar76"],
    capabilities=[
        Capability(
            capability_id="fermat.route@v1",
            product_id="prod-fermat",
            description=(
                "Compute the globally least-time (least-cost) composition path from "
                "'start' to 'goal' over a directed weighted service graph, plus the "
                "eikonal potential T(v) for every node and a dual optimality "
                "certificate. Edge weight is the refractive index n(u,v) >= 0 "
                "(cost + latency + risk). Returns path, total, potentials, "
                "graph_commitment and certificate{path_edges,...} for trustless replay."
            ),
            handler=_route,
            input_schema={
                "type": "object",
                "required": ["edges", "start", "goal"],
                "properties": {
                    "nodes": {"type": "array", "items": _NODE,
                              "description": "Optional explicit node labels (e.g. isolated nodes)."},
                    "edges": _EDGES_SCHEMA,
                    "start": _NODE,
                    "goal": _NODE,
                    "blend": _BLEND_SCHEMA,
                },
            },
            output_schema={
                "type": "object",
                "required": ["path", "total", "potentials", "graph_commitment", "certificate"],
                "properties": {
                    "start": {"type": "string"}, "goal": {"type": "string"},
                    "reachable": {"type": "boolean"},
                    "path": {"type": ["array", "null"], "items": {"type": "string"}},
                    "total": {"type": ["number", "null"]},
                    "potentials": _POTENTIALS_SCHEMA,
                    "graph_commitment": {"type": "string"},
                    "n": {"type": "integer"}, "m": {"type": "integer"},
                    "blend": {"type": "object"},
                    "certificate": {
                        "type": "object",
                        "properties": {
                            "kind": {"type": "string"},
                            "path_edges": {"type": "array"},
                            "feasibility": {"type": "string"},
                            "tightness": {"type": "string"},
                        },
                    },
                },
            },
            price_per_call_usd=0.01,
            p50_latency_ms=50,
            success_rate_30d=0.999,
        ),
        Capability(
            capability_id="fermat.verify@v1",
            product_id="prod-fermat",
            description=(
                "Trustless verification of a least-time route via its dual certificate. "
                "Re-derives the canonical graph and refractive indices, then checks the "
                "supplied potentials T(v) for FEASIBILITY (T(v) <= T(u)+n(u,v) on every "
                "edge) and the supplied path for TIGHTNESS (T(v) == T(u)+n(u,v) on every "
                "path edge, grounded T(start)=0). Both holding proves the path is "
                "globally optimal — checked in O(E), no Dijkstra, no trust in the oracle."
            ),
            handler=_verify,
            input_schema={
                "type": "object",
                "required": ["edges", "potentials", "start", "goal"],
                "properties": {
                    "nodes": {"type": "array", "items": _NODE},
                    "edges": _EDGES_SCHEMA,
                    "path": {"type": "array", "items": _NODE,
                             "description": "Claimed optimal path start -> goal (node labels in order)."},
                    "potentials": _POTENTIALS_SCHEMA,
                    "start": _NODE,
                    "goal": _NODE,
                    "total": {"type": "number", "description": "Optional claimed total to match against T(goal)."},
                    "blend": _BLEND_SCHEMA,
                },
            },
            output_schema={
                "type": "object",
                "required": ["valid", "feasible", "tight", "graph_commitment"],
                "properties": {
                    "valid": {"type": "boolean"},
                    "feasible": {"type": "boolean"},
                    "tight": {"type": "boolean"},
                    "source_grounded": {"type": "boolean"},
                    "graph_commitment": {"type": "string"},
                    "recomputed_total": {"type": ["number", "null"]},
                    "claimed_total": {"type": ["number", "null"]},
                    "first_violation": {"type": ["array", "null"]},
                    "edges_checked": {"type": "integer"},
                    "reasons": {"type": "array", "items": {"type": "string"}},
                },
            },
            price_per_call_usd=0.001,
            p50_latency_ms=20,
            success_rate_30d=0.999,
        ),
    ],
)
