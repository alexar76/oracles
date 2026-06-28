"""Fourier oracle spec — graph-spectral (Laplacian spectrum / Fiedler) capabilities."""

from __future__ import annotations

import os
from typing import Any

from oracle_core import Capability, OracleSpec

from fourier import spectral


def _spectrum(d: dict[str, Any]) -> dict[str, Any]:
    edges = d.get("edges")
    if edges is None:
        raise ValueError("missing 'edges'")
    return spectral.analyze(
        nodes=d.get("nodes"),
        edges=edges,
        laplacian_kind=str(d.get("laplacian", "normalized")),
        k=int(d.get("k", spectral.DEFAULT_K)),
    )


def _verify(d: dict[str, Any]) -> dict[str, Any]:
    edges = d.get("edges")
    if edges is None:
        raise ValueError("missing 'edges'")
    if "lambda" not in d:
        raise ValueError("missing 'lambda'")
    if "vector" not in d:
        raise ValueError("missing 'vector'")
    return spectral.verify(
        nodes=d.get("nodes"),
        edges=edges,
        lambda_=float(d["lambda"]),
        vector=list(d["vector"]),
        laplacian_kind=str(d.get("laplacian", "normalized")),
        tol=float(d.get("tol", spectral.DEFAULT_TOL)),
    )


_GRAPH_SCHEMA = {
    "nodes": {
        "type": "array",
        "description": "Optional explicit node labels (covers isolated nodes that have no edges).",
        "items": {"type": ["string", "integer"]},
    },
    "edges": {
        "type": "array",
        "description": "Undirected edges as [u, v] label pairs, or weighted [u, v, w] triples.",
        "items": {
            "type": "array",
            "minItems": 2,
            "maxItems": 3,
            "items": {"type": ["string", "integer", "number"]},
        },
    },
    "laplacian": {
        "type": "string",
        "enum": list(spectral.LAPLACIANS),
        "default": "normalized",
        "description": "Symmetric normalized (scale-invariant, spectrum [0,2]) or combinatorial L = D − A.",
    },
}


SPEC = OracleSpec(
    name="Fourier Graph-Spectral Oracle",
    product_id="prod-fourier",
    description=(
        "The Fourier transform on a graph. Computes the Laplacian spectrum (L = D − A, "
        "or the symmetric normalized L_sym), the algebraic connectivity λ₂ (Fiedler "
        "value — exactly 0 iff disconnected, small near a bottleneck), the Fiedler "
        "vector and its sign-based spectral bisection (cut size + conductance), and a "
        "per-node spectral embedding (v₂, v₃, v₄). Exposes the global 'how close is this "
        "network to splitting' structure that no per-node metric captures. Eigenpairs "
        "are certified trustlessly in O(E) without re-running the eigendecomposition."
    ),
    public_url=os.environ.get("FOURIER_PUBLIC_URL", "http://localhost:9315"),
    categories=["graph-spectral", "spectral-clustering", "connectivity", "graph-analytics", "agent-tooling"],
    signing_key_path=os.environ.get("FOURIER_SIGNING_KEY", "data/fourier_signing_key"),
    related=["https://github.com/alexar76"],
    capabilities=[
        Capability(
            capability_id="fourier.spectrum@v1",
            product_id="prod-fourier",
            description=(
                "Spectral analysis of a graph. Builds the (normalized or combinatorial) "
                "Laplacian, runs an exact symmetric eigendecomposition (numpy.linalg.eigh), "
                "and returns the bottom k eigenvalues, the Fiedler value λ₂ and Fiedler "
                "vector, the spectral cut (two sets + cut size + conductance), and the "
                "(v₂, v₃, v₄) spectral embedding per node. The combinatorial λ₂ is always "
                "reported alongside. Includes a graph_commitment for trustless replay."
            ),
            handler=_spectrum,
            input_schema={
                "type": "object",
                "required": ["edges"],
                "properties": {
                    **_GRAPH_SCHEMA,
                    "k": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": spectral.MAX_NODES,
                        "default": spectral.DEFAULT_K,
                        "description": "Number of smallest eigenvalues to return.",
                    },
                },
            },
            output_schema={
                "type": "object",
                "required": ["n", "m", "laplacian", "eigenvalues", "fiedler_value", "graph_commitment"],
                "properties": {
                    "n": {"type": "integer"},
                    "m": {"type": "integer"},
                    "laplacian": {"type": "string"},
                    "eigenvalues": {"type": "array", "items": {"type": "number"}},
                    "fiedler_value": {"type": "number"},
                    "combinatorial_lambda2": {"type": "number"},
                    "fiedler_vector": {"type": "array", "items": {"type": "number"}},
                    "spectral_cut": {
                        "type": "object",
                        "properties": {
                            "set_a": {"type": "array", "items": {"type": "string"}},
                            "set_b": {"type": "array", "items": {"type": "string"}},
                            "cut_size": {"type": "number"},
                            "conductance": {"type": "number"},
                        },
                    },
                    "embedding": {
                        "type": "array",
                        "items": {"type": "array", "items": {"type": "number"}},
                    },
                    "nodes": {"type": "array", "items": {"type": "string"}},
                    "graph_commitment": {"type": "string"},
                },
            },
            price_per_call_usd=0.005,
            p50_latency_ms=40,
            success_rate_30d=0.999,
        ),
        Capability(
            capability_id="fourier.verify@v1",
            product_id="prod-fourier",
            description=(
                "Trustless eigenpair certificate. Given the graph and a claimed (λ, x), "
                "checks the eigen-relation ‖L x − λ x‖ / ‖x‖ ≤ tol and that x is "
                "orthogonal to the trivial λ₁ eigenvector (so it is genuinely the "
                "connectivity / Fiedler mode). Certifies λ₂ in O(E) — no full "
                "eigendecomposition, no trust in the oracle."
            ),
            handler=_verify,
            input_schema={
                "type": "object",
                "required": ["edges", "lambda", "vector"],
                "properties": {
                    **_GRAPH_SCHEMA,
                    "lambda": {"type": "number", "description": "Claimed eigenvalue to certify."},
                    "vector": {
                        "type": "array",
                        "items": {"type": "number"},
                        "description": "Claimed eigenvector, in the canonical (sorted-label) node order.",
                    },
                    "tol": {"type": "number", "default": spectral.DEFAULT_TOL},
                },
            },
            output_schema={
                "type": "object",
                "required": ["valid", "residual", "orthogonality", "graph_commitment"],
                "properties": {
                    "valid": {"type": "boolean"},
                    "residual": {"type": "number"},
                    "orthogonality": {"type": "number"},
                    "is_eigenpair": {"type": "boolean"},
                    "graph_commitment": {"type": "string"},
                    "error": {"type": "string"},
                },
            },
            price_per_call_usd=0.001,
            p50_latency_ms=10,
            success_rate_30d=0.999,
        ),
    ],
)
