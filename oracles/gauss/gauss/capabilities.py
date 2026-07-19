"""Gauss oracle spec — Gaussian-Process posterior + Expected-Improvement capabilities."""

from __future__ import annotations

import os
from typing import Any

from oracle_core import Capability, OracleSpec

from gauss import gp


def _field(d: dict[str, Any]) -> dict[str, Any]:
    return gp.field(d)


def _suggest(d: dict[str, Any]) -> dict[str, Any]:
    return gp.suggest(d)


def _verify(d: dict[str, Any]) -> dict[str, Any]:
    return gp.verify(d)


# Shared schema fragments. The protocol layer does NOT validate input against
# input_schema — the handlers in gp.py raise ValueError on bad input and clamp
# array sizes (MAX_OBS observations, MAX_QUERY query points) — so this is
# documentation for discovery clients, not an enforcement boundary.
_POINTS = {"type": "array", "items": {"type": "array", "items": {"type": "number"}}}
_HYPERPARAMS = {
    "type": "object",
    "description": "Optional RBF-kernel hyperparameters; sane / heuristic defaults fill any omitted.",
    "properties": {
        "length_scale": {"type": "number", "exclusiveMinimum": 0,
                         "description": "RBF length-scale l (default: median pairwise distance)."},
        "signal_var": {"type": "number", "exclusiveMinimum": 0,
                       "description": "Signal variance sigma_f^2 (default: var(y))."},
        "noise_var": {"type": "number", "exclusiveMinimum": 0,
                      "description": "Observation noise sigma_n^2 (default: 1e-6)."},
    },
}
_HP_OUT = {
    "type": "object",
    "properties": {
        "length_scale": {"type": "number"},
        "signal_var": {"type": "number"},
        "noise_var": {"type": "number"},
    },
}


SPEC = OracleSpec(
    name="Gauss Gaussian-Process Oracle",
    product_id="prod-gauss",
    description=(
        "Gaussian-Process regression: a principled posterior over functions from sparse, "
        "noisy observations. Returns the predictive mean and calibrated variance "
        "everywhere (uncertainty that is small at data and rises to the prior far from "
        "it), and — via Expected Improvement — the single best next point to sample. A "
        "principled replacement for hand-rolled UCB / bandit exploration. RBF kernel, "
        "Cholesky-based, pure numpy; every posterior is trustlessly replayable."
    ),
    public_url=os.environ.get("GAUSS_PUBLIC_URL", "http://localhost:9311"),
    categories=["gaussian-process", "uncertainty", "active-learning", "bayesian-optimization", "agent-tooling"],
    signing_key_path=os.environ.get("GAUSS_SIGNING_KEY", "data/gauss_signing_key"),
    related=["https://github.com/alexar76"],
    capabilities=[
        Capability(
            capability_id="gauss.field@v1",
            product_id="prod-gauss",
            description=(
                "GP posterior over a query field. Fits the RBF kernel to (X, y) and "
                "returns the predictive mean and variance (and std) at every query point "
                "— the calibrated uncertainty band that collapses to the noise floor at "
                "observations and breathes out to the prior sigma_f^2 far from data."
            ),
            handler=_field,
            input_schema={
                "type": "object",
                "required": ["X", "y", "query"],
                "properties": {
                    "X": {**_POINTS, "description": "Training inputs (n × d)."},
                    "y": {"type": "array", "items": {"type": "number"}, "description": "Training targets (n)."},
                    "query": {**_POINTS, "description": "Query inputs (m × d) to predict at."},
                    "hyperparams": _HYPERPARAMS,
                },
            },
            output_schema={
                "type": "object",
                "required": ["mean", "var", "std", "n", "d"],
                "properties": {
                    "mean": {"type": "array", "items": {"type": "number"}},
                    "var": {"type": "array", "items": {"type": "number"}},
                    "std": {"type": "array", "items": {"type": "number"}},
                    "hyperparams": _HP_OUT,
                    "n": {"type": "integer"},
                    "d": {"type": "integer"},
                },
            },
            price_per_call_usd=0.006,
            p50_latency_ms=25,
            success_rate_30d=0.999,
        ),
        Capability(
            capability_id="gauss.suggest@v1",
            product_id="prod-gauss",
            description=(
                "Best next experiment by Expected Improvement. Given (X, y) and either an "
                "explicit candidate set or bounds+grid, fits the GP and ranks candidates by "
                "EI(x) = (mu - f_best - xi)·Phi(z) + std·phi(z). Returns the argmax point, "
                "its EI, and the full acquisition vector — a calibrated alternative to "
                "hand-tuned UCB / bandit exploration. Supports max or min goals."
            ),
            handler=_suggest,
            input_schema={
                "type": "object",
                "required": ["X", "y"],
                "properties": {
                    "X": {**_POINTS, "description": "Training inputs (n × d)."},
                    "y": {"type": "array", "items": {"type": "number"}, "description": "Training targets (n)."},
                    "candidates": {**_POINTS, "description": "Explicit candidate points (c × d)."},
                    "bounds": {"type": "array", "items": {"type": "array", "minItems": 2, "maxItems": 2,
                               "items": {"type": "number"}},
                               "description": "Per-dimension [lo, hi] box, swept by an auto grid (alternative to candidates)."},
                    "grid": {"type": "integer", "minimum": 2, "default": 64,
                             "description": "Per-axis grid resolution when using bounds (capped to stay bounded)."},
                    "xi": {"type": "number", "minimum": 0, "default": 0.01,
                           "description": "EI exploration margin."},
                    "goal": {"type": "string", "enum": ["max", "min"], "default": "max"},
                    "hyperparams": _HYPERPARAMS,
                },
            },
            output_schema={
                "type": "object",
                "required": ["best", "ei", "acquisition", "index"],
                "properties": {
                    "best": {"type": "array", "items": {"type": "number"}},
                    "ei": {"type": "number"},
                    "acquisition": {"type": "array", "items": {"type": "number"}},
                    "index": {"type": "integer"},
                    "goal": {"type": "string"},
                    "f_best": {"type": "number"},
                    "n_candidates": {"type": "integer"},
                    "hyperparams": _HP_OUT,
                },
            },
            price_per_call_usd=0.006,
            p50_latency_ms=25,
            success_rate_30d=0.999,
        ),
        Capability(
            capability_id="gauss.verify@v1",
            product_id="prod-gauss",
            description=(
                "Trustless replay: recompute the GP posterior at one or a few query points "
                "and check the claimed mean / variance match within a tolerance. Cheap; "
                "needs no trust in the oracle that produced the original field."
            ),
            handler=_verify,
            input_schema={
                "type": "object",
                "required": ["X", "y", "query"],
                "properties": {
                    "X": {**_POINTS, "description": "Training inputs (n × d)."},
                    "y": {"type": "array", "items": {"type": "number"}, "description": "Training targets (n)."},
                    "query": {**_POINTS, "description": "Query inputs (m × d) to recompute at."},
                    "claimed_mean": {"type": "array", "items": {"type": "number"},
                                     "description": "Claimed posterior mean to check."},
                    "claimed_var": {"type": "array", "items": {"type": "number"},
                                    "description": "Claimed posterior variance to check."},
                    "tol": {"type": "number", "default": 1e-6, "description": "Max absolute error allowed."},
                    "hyperparams": _HYPERPARAMS,
                },
            },
            output_schema={
                "type": "object",
                "required": ["valid", "recomputed_mean", "recomputed_var", "max_abs_err"],
                "properties": {
                    "valid": {"type": "boolean"},
                    "recomputed_mean": {"type": "array", "items": {"type": "number"}},
                    "recomputed_var": {"type": "array", "items": {"type": "number"}},
                    "max_abs_err": {"type": "number"},
                    "tol": {"type": "number"},
                },
            },
            price_per_call_usd=0.001,
            p50_latency_ms=8,
            success_rate_30d=0.999,
        ),
    ],
)
