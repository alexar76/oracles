"""Kantor oracle spec — exact optimal transport (Wasserstein) with a Kantorovich dual certificate."""

from __future__ import annotations

import os
from typing import Any

from oracle_core import Capability, OracleSpec

from kantor import transport


def _transport(d: dict[str, Any]) -> dict[str, Any]:
    if d.get("a") is None:
        raise ValueError("missing 'a' (source distribution weights)")
    if d.get("b") is None:
        raise ValueError("missing 'b' (sink distribution weights)")
    if d.get("cost") is None and (d.get("source_points") is None or d.get("sink_points") is None):
        raise ValueError("provide either 'cost' (m*n matrix) or 'source_points'+'sink_points'")
    return transport.transport(d)


def _verify(d: dict[str, Any]) -> dict[str, Any]:
    if d.get("a") is None or d.get("b") is None:
        raise ValueError("missing 'a'/'b'")
    if d.get("cost") is None and (d.get("source_points") is None or d.get("sink_points") is None):
        raise ValueError("provide either 'cost' (m*n matrix) or 'source_points'+'sink_points'")
    if d.get("claimed_cost") is None:
        raise ValueError("missing 'claimed_cost'")
    if d.get("potentials") is None:
        raise ValueError("missing 'potentials' (the dual certificate {u, v})")
    if d.get("plan") is None:
        raise ValueError(
            "missing 'plan' (the primal transport plan P; required alongside the dual "
            "potentials for a two-sided optimality certificate)"
        )
    return transport.verify(d)


_VEC = {"type": "array", "items": {"type": "number"}}
_COST_SCHEMA = {
    "type": "array",
    "description": "Explicit m*n ground-cost matrix C (non-negative). Mutually exclusive with points.",
    "items": _VEC,
}
_POINTS_SCHEMA = {
    "type": "array",
    "description": "Point coordinates (k-D); the cost matrix is derived via 'metric' and 'p'.",
    "items": {"oneOf": [_VEC, {"type": "number"}]},
}
_POTENTIALS_SCHEMA = {
    "type": "object",
    "description": "Kantorovich dual potentials: u over sources (len m), v over sinks (len n).",
    "properties": {"u": _VEC, "v": _VEC},
    "required": ["u", "v"],
}
_PLAN_SCHEMA = {
    "type": "array",
    "description": (
        "Primal transport plan P (m*n, row-sums==a, col-sums==b, P>=0). Required by "
        "kantor.verify: it upper-bounds the optimum so a dual-only cert can't under-report."
    ),
    "items": _VEC,
}


SPEC = OracleSpec(
    name="Kantor Optimal-Transport Oracle",
    product_id="prod-kantor",
    description=(
        "Exact discrete optimal transport (the Wasserstein / earth-mover's distance) with "
        "a verifiable Kantorovich DUAL certificate. Given a source distribution a, a sink "
        "distribution b and a ground cost C (supplied directly or computed from point "
        "coordinates for the p-Wasserstein W_p), Kantor solves the transport LP EXACTLY by "
        "pure-Python MIN-COST FLOW (successive shortest paths) — no Sinkhorn, no scipy — and "
        "returns the optimal transport plan P, the cost (and W_p when the cost is a p-th "
        "power of a metric), and the Kantorovich potentials (u, v). The plan and potentials "
        "together form a two-sided LP optimality certificate: a verifier checks the plan is "
        "primal-feasible (P>=0, marginals a,b) with <P,C> == cost (an upper bound) AND the "
        "dual is feasible u_i + v_j <= C_ij on EVERY pair with cost == sum a_i u_i + sum b_j "
        "v_j (a lower bound), both in O(m*n), thereby certifying global optimality WITHOUT "
        "re-solving and without trusting the oracle (a dual-only check would accept an "
        "under-reported cost). An explicitly-labelled approximate entropic Sinkhorn path is "
        "also offered (method='sinkhorn') and is never passed off as exact. The optimal-"
        "transport analogue of Fermat's least-time dual certificate."
    ),
    public_url=os.environ.get("KANTOR_PUBLIC_URL", "http://localhost:9314"),
    categories=["optimal-transport", "wasserstein", "optimization", "matching", "agent-tooling"],
    signing_key_path=os.environ.get("KANTOR_SIGNING_KEY", "data/kantor_signing_key"),
    related=["https://github.com/alexar76"],
    capabilities=[
        Capability(
            capability_id="kantor.transport@v1",
            product_id="prod-kantor",
            description=(
                "Solve the discrete optimal-transport problem from source distribution a to "
                "sink distribution b under ground cost C (or points + metric/p). Returns the "
                "optimal transport plan, the cost, the p-Wasserstein distance (when the cost "
                "is a p-th power of a metric), and the Kantorovich dual potentials (u, v) — "
                "the certificate. method='exact' (default) is solved by min-cost flow and is "
                "certifiable; method='sinkhorn' is an explicitly approximate entropic upper "
                "bound carrying its regulariser eps."
            ),
            handler=_transport,
            input_schema={
                "type": "object",
                "required": ["a", "b"],
                "properties": {
                    "a": {**_VEC, "description": "Source distribution weights (len m; renormalised to sum 1)."},
                    "b": {**_VEC, "description": "Sink distribution weights (len n; renormalised to sum 1)."},
                    "cost": _COST_SCHEMA,
                    "source_points": _POINTS_SCHEMA,
                    "sink_points": _POINTS_SCHEMA,
                    "p": {"type": "number", "minimum": 0, "default": 2,
                          "description": "Order of the Wasserstein distance (W_p); ground cost = distance**p."},
                    "metric": {"type": "string", "enum": ["euclidean", "sqeuclidean"], "default": "euclidean"},
                    "method": {"type": "string", "enum": ["exact", "sinkhorn"], "default": "exact"},
                    "eps": {"type": "number", "minimum": 0, "default": 0.1,
                            "description": "Entropic regulariser for method='sinkhorn' (smaller = closer to exact)."},
                },
            },
            output_schema={
                "type": "object",
                "required": ["method", "cost", "plan", "potentials", "m", "n"],
                "properties": {
                    "method": {"type": "string"},
                    "cost": {"type": "number"},
                    "wasserstein": {"type": ["number", "null"]},
                    "plan": {"type": "array", "items": _VEC},
                    "potentials": _POTENTIALS_SCHEMA,
                    "dual_objective": {"type": "number"},
                    "m": {"type": "integer"}, "n": {"type": "integer"},
                    "p": {"type": "number"}, "metric": {"type": ["string", "null"]},
                    "approximate": {"type": "boolean"},
                    "regularizer_eps": {"type": "number"},
                    "certificate": {"type": "object"},
                },
            },
            price_per_call_usd=0.006,
            p50_latency_ms=60,
            success_rate_30d=0.999,
        ),
        Capability(
            capability_id="kantor.verify@v1",
            product_id="prod-kantor",
            description=(
                "Trustless verification of an optimal-transport cost via a TWO-SIDED "
                "primal-dual certificate. Given a, b, C (or points), a claimed_cost, the "
                "transport plan P and the Kantorovich potentials (u, v), checks PRIMAL "
                "FEASIBILITY (P>=0, row-sums==a, col-sums==b) with <P,C> == claimed_cost (an "
                "upper bound) AND DUAL FEASIBILITY u_i + v_j <= C_ij on every (i,j) with "
                "claimed_cost == sum a_i u_i + sum b_j v_j (a lower bound). Both bounds "
                "meeting at claimed_cost certifies the exact optimum; a dual-only check would "
                "accept an under-reported cost. Checked in O(m*n), no re-solve, no trust."
            ),
            handler=_verify,
            input_schema={
                "type": "object",
                "required": ["a", "b", "claimed_cost", "plan", "potentials"],
                "properties": {
                    "a": _VEC,
                    "b": _VEC,
                    "cost": _COST_SCHEMA,
                    "source_points": _POINTS_SCHEMA,
                    "sink_points": _POINTS_SCHEMA,
                    "p": {"type": "number", "minimum": 0, "default": 2},
                    "metric": {"type": "string", "enum": ["euclidean", "sqeuclidean"], "default": "euclidean"},
                    "claimed_cost": {"type": "number", "description": "The transport cost to certify."},
                    "plan": _PLAN_SCHEMA,
                    "potentials": _POTENTIALS_SCHEMA,
                    "tol": {"type": "number", "default": 1e-6,
                            "description": "Relative tolerance (scaled by max|C| for cost checks) for feasibility, duality and the primal-cost match."},
                },
            },
            output_schema={
                "type": "object",
                "required": ["valid", "dual_objective", "primal_cost", "claimed_cost", "max_violation"],
                "properties": {
                    "valid": {"type": "boolean"},
                    "feasible": {"type": "boolean"},
                    "strong_duality": {"type": "boolean"},
                    "primal_feasible": {"type": "boolean"},
                    "primal_cost_matches": {"type": "boolean"},
                    "dual_objective": {"type": "number"},
                    "primal_cost": {"type": "number"},
                    "claimed_cost": {"type": "number"},
                    "max_violation": {"type": "number"},
                    "duality_gap": {"type": "number"},
                    "primal_gap": {"type": "number"},
                    "marginal_violation": {"type": "number"},
                    "min_plan_entry": {"type": "number"},
                    "m": {"type": "integer"}, "n": {"type": "integer"},
                },
            },
            price_per_call_usd=0.001,
            p50_latency_ms=10,
            success_rate_30d=0.999,
        ),
    ],
)
