"""Chronos oracle spec — verifiable delay (VDF) capabilities on oracle-core."""

from __future__ import annotations

import os
from typing import Any

from oracle_core import Capability, OracleSpec

from chronos import vdf


def _eval(d: dict[str, Any]) -> dict[str, Any]:
    # Clamp to the declared schema bounds [1, MAX_DIFFICULTY]. The protocol layer
    # does not validate input against input_schema, so enforce the ceiling here —
    # otherwise a caller can request an unbounded number of sequential squarings
    # and pin a CPU for an arbitrarily long time.
    difficulty = max(1, min(int(d.get("difficulty", 100_000)), vdf.MAX_DIFFICULTY))
    return vdf.run(str(d.get("seed", "")), difficulty)


def _verify(d: dict[str, Any]) -> dict[str, Any]:
    try:
        g = int(d["g"])
        y = int(d["y"])
        T = int(d["difficulty"])
        pi = int(d["proof"]["pi"])
        l = int(d["proof"]["l"])
    except (KeyError, ValueError, TypeError) as exc:
        return {"valid": False, "error": f"malformed proof: {exc}"}
    return {"valid": vdf.verify(g, y, T, pi, l)}


SPEC = OracleSpec(
    name="Chronos VDF Oracle",
    product_id="prod-chronos",
    description=(
        "Verifiable delay function (Wesolowski VDF over the RSA-2048 unfactored "
        "modulus). Proof-of-elapsed-sequential-work: fair ordering, timeouts, and "
        "unbiasable randomness. Publicly verifiable — no trust in the oracle."
    ),
    public_url=os.environ.get("CHRONOS_PUBLIC_URL", "http://localhost:9300"),
    categories=["verifiable-delay", "ordering", "randomness-beacon", "agent-tooling"],
    signing_key_path=os.environ.get("CHRONOS_SIGNING_KEY", "data/chronos_signing_key"),
    related=["https://github.com/alexar76"],
    capabilities=[
        Capability(
            capability_id="chronos.eval@v1",
            product_id="prod-chronos",
            # Spells out "verifiable delay function" rather than only the acronym: a buyer
            # searching the words — "verifiable delay proof" — matched nothing here and got
            # a randomness oracle instead. The expansion is what people type; VDF is what
            # they type once they already know the answer.
            description=(
                "Verifiable delay function (VDF): proof that real sequential time passed. "
                "Evaluates y = g^(2^T) mod N via T sequential squarings, returning y + a "
                "Wesolowski proof. Higher difficulty = more enforced sequential time. "
                "Anyone can verify without redoing the work."
            ),
            handler=_eval,
            input_schema={
                "type": "object",
                "required": ["seed"],
                "properties": {
                    "seed": {"type": "string", "minLength": 1},
                    "difficulty": {"type": "integer", "minimum": 1, "maximum": vdf.MAX_DIFFICULTY, "default": 100000},
                },
            },
            output_schema={
                "type": "object",
                "required": ["g", "y", "difficulty", "proof"],
                "properties": {
                    "scheme": {"type": "string"},
                    "g": {"type": "string"},
                    "y": {"type": "string"},
                    "difficulty": {"type": "integer"},
                    "proof": {"type": "object"},
                    "modulus": {"type": "string"},
                },
            },
            # ── Cost controls (oracle_core.tiers) ────────────────────────────────
            # Measured on the reference box: difficulty 1_000 → 8.2 ms, 10_000 → 69 ms,
            # 100_000 → 680 ms, and MAX_DIFFICULTY 1_000_000 → 6.8 s. Sequential by
            # construction — a call pins one core for its whole duration and no hardware
            # parallelises it away.
            #
            # The free ceiling is the schema's own default, deliberately: a caller who
            # sends no `difficulty` is never refused, and the free tier demonstrates the
            # primitive completely (the proof verifies, the delay is real, the receipt is
            # signed) at a tenth of the cost. The full million is what payment buys.
            free_tier_max={"difficulty": 100_000},
            # Cost is linear in difficulty and nothing else: ~147 squarings per ms on the
            # reference box, straight off the four measurements above (8.2 ms at 1_000
            # through 6.8 s at 1_000_000 all land on the same line). Budgets are then in
            # CPU-ms, so the arithmetic below is checkable against those numbers.
            cost_ms=lambda d: max(1, int(d.get("difficulty", 100_000) or 0)) / 147.0,
            # 20 s of CPU per minute per client = a third of a core. That is three
            # max-difficulty evaluations, or 29 at the free ceiling, or ~2400 at the
            # difficulty=1_000 a developer explores with — which is the point of
            # budgeting work instead of calls: the cheap case stops being punished.
            cpu_budget_ms_per_min=20_000,
            # One core, in aggregate, for this capability. Per-IP budgets do not bind a
            # proxy fleet; this does. Raise it (with hardware) if paid volume justifies.
            global_cpu_budget_ms_per_min=60_000,
            price_per_call_usd=0.01,
            p50_latency_ms=400,
            success_rate_30d=0.999,
        ),
        Capability(
            capability_id="chronos.verify@v1",
            product_id="prod-chronos",
            description=(
                "Verify a verifiable delay function (VDF) proof (π^l · g^r ≡ y) — cheap "
                "and trustless, no need to redo the sequential work."
            ),
            handler=_verify,
            input_schema={
                "type": "object",
                "required": ["g", "y", "difficulty", "proof"],
                "properties": {
                    "g": {"type": "string"},
                    "y": {"type": "string"},
                    "difficulty": {"type": "integer"},
                    "proof": {"type": "object"},
                },
            },
            output_schema={"type": "object", "required": ["valid"], "properties": {"valid": {"type": "boolean"}}},
            price_per_call_usd=0.001,
            p50_latency_ms=15,
            success_rate_30d=0.999,
        ),
    ],
)
