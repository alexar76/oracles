"""Aestus oracle spec — RSW time-lock puzzle capabilities on oracle-core."""

from __future__ import annotations

import os
from typing import Any

from oracle_core import Capability, OracleSpec

from aestus import rsw


def _seal(d: dict[str, Any]) -> dict[str, Any]:
    # The protocol layer does NOT validate input against input_schema, so the
    # handler enforces required fields and clamps T to [1, MAX_T] — otherwise a
    # caller could request an unbounded number of sequential squarings and pin a
    # CPU for an arbitrarily long time (exactly how Chronos clamps difficulty).
    data = d.get("data")
    if data is None:
        raise ValueError("missing 'data'")
    encoding = str(d.get("encoding", "utf8"))
    T = max(1, min(int(d.get("T", 1_000_000)), rsw.MAX_T))
    modulus_bits = int(d.get("modulus_bits", rsw.DEFAULT_MODULUS_BITS))
    return rsw.seal(str(data), T, encoding=encoding, modulus_bits=modulus_bits)


def _open(d: dict[str, Any]) -> dict[str, Any]:
    puzzle = d.get("puzzle")
    if puzzle is None:
        raise ValueError("missing 'puzzle'")
    return rsw.open_puzzle(puzzle)


def _verify(d: dict[str, Any]) -> dict[str, Any]:
    puzzle = d.get("puzzle")
    if puzzle is None:
        raise ValueError("missing 'puzzle'")
    b = d.get("b")
    if b is None:
        raise ValueError("missing 'b' (claimed result of the squarings)")
    return rsw.verify(puzzle, str(b))


def _modulus_cost_factor(d: Any) -> float:
    """(bits / 2048)^2 — a modular squaring is quadratic in the modulus width.

    Read from N itself, never from the caller-declared ``modulus_bits`` label. Falls back
    to 1.0 when N is absent or unparseable (CPython refuses int() on >4300-digit strings),
    which is safe because rsw._parse_puzzle then refuses the puzzle anyway.
    """
    raw = _nested(d, "puzzle", "N")
    try:
        bits = int(raw).bit_length()
    except (TypeError, ValueError):
        return 1.0
    if bits <= 0:
        return 1.0
    return max(1.0, (bits / 2048.0) ** 2)


def _int_or(value: Any, default: int) -> int:
    """Best-effort int for cost estimation — a malformed value is the handler's to
    reject, and estimating its cost as the cheap default is correct: the request is
    about to be refused for free."""
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return default


def _nested(d: dict[str, Any], *path: str) -> Any:
    cur: Any = d
    for part in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def _seal_cost_ms(d: dict[str, Any]) -> float:
    """CPU-ms a seal will cost: T sequential squarings, plus fresh prime generation.

    Both terms matter. A caller who sends T=1 and modulus_bits=3072 does no squaring
    worth counting but still costs ~2.7 s of prime search, so a T-only estimate would
    hand out that cost for free — see the cost-control note on the capability.
    """
    T = _int_or(d.get("T", 1_000_000), 1_000_000)
    bits = _int_or(d.get("modulus_bits", rsw.DEFAULT_MODULUS_BITS), rsw.DEFAULT_MODULUS_BITS)
    # Observed medians: 600 ms at 2048 bits, 2700 ms at 3072. Prime search cost grows
    # much faster than linearly in the bit length, so interpolating between the two
    # measured points would understate 3072; take the nearer measured point instead.
    modulus_ms = 2700.0 if bits > 2560 else 600.0
    return T / 137.0 + modulus_ms


_PUZZLE_SCHEMA = {
    "type": "object",
    "required": ["N", "a", "T", "ciphertext", "key_commitment"],
    "properties": {
        "scheme": {"type": "string"},
        "N": {"type": "string", "description": "Fresh RSA modulus N=p·q (factors burned at seal)."},
        "a": {"type": "string", "description": "Base; b = a^(2^T) mod N."},
        "T": {"type": "integer", "minimum": 1, "maximum": rsw.MAX_T},
        "ciphertext": {"type": "string", "description": "hex; plaintext XOR SHA256-CTR(key)."},
        "key_commitment": {"type": "string", "description": "SHA256 commitment binding the unlock value b."},
        "modulus_bits": {"type": "integer"},
        "encoding": {"type": "string", "enum": ["utf8", "hex"]},
    },
}


SPEC = OracleSpec(
    name="Aestus Time-Lock Oracle",
    product_id="prod-aestus",
    description=(
        "Rivest-Shamir-Wagner time-lock puzzles. SEAL data so NOBODY can open it "
        "before ~T sequential squarings of wall-clock have elapsed — then ANYONE "
        "can open it, with no trapdoor holder. Where Chronos proves the PAST "
        "elapsed, Aestus locks the FUTURE. Trustless by construction: each seal "
        "generates a FRESH RSA modulus N=p·q, derives the key by T sequential "
        "squarings (the honest slow path, NOT the φ(N) shortcut), and BURNS p,q,φ "
        "— so not even the oracle can open early. Honest tradeoff: because φ is "
        "burned, sealing costs the SAME T squarings as opening (seal-work == "
        "open-work); the φ shortcut would make sealing O(1) but would let the "
        "operator decrypt early, so we refuse to take it. Pure Python."
    ),
    public_url=os.environ.get("AESTUS_PUBLIC_URL", "http://localhost:9312"),
    categories=["time-lock", "timed-release", "delay-encryption", "agent-tooling"],
    signing_key_path=os.environ.get("AESTUS_SIGNING_KEY", "data/aestus_signing_key"),
    related=["https://github.com/alexar76"],
    capabilities=[
        Capability(
            capability_id="aestus.seal@v1",
            product_id="prod-aestus",
            description=(
                "Time-lock data: generate a fresh modulus N, compute b = a^(2^T) "
                "mod N via T sequential squarings, encrypt under SHA256(b), and "
                "burn the factorization. Returns a self-contained puzzle anyone can "
                "later open — the trapdoor is never returned (so the oracle cannot "
                "open early). Higher T = longer enforced delay before unlock."
            ),
            handler=_seal,
            input_schema={
                "type": "object",
                "required": ["data"],
                "properties": {
                    "data": {"type": "string", "minLength": 0,
                             "description": "Plaintext to seal (utf8 string, or hex if encoding='hex')."},
                    "encoding": {"type": "string", "enum": ["utf8", "hex"], "default": "utf8"},
                    "T": {"type": "integer", "minimum": 1, "maximum": rsw.MAX_T, "default": 1_000_000,
                          "description": "Sequential squarings = enforced delay before the puzzle opens."},
                    "modulus_bits": {"type": "integer", "minimum": rsw.MIN_MODULUS_BITS,
                                     "maximum": rsw.MAX_MODULUS_BITS, "default": rsw.DEFAULT_MODULUS_BITS},
                },
            },
            output_schema={
                "type": "object",
                "required": ["scheme", "N", "a", "T", "ciphertext", "key_commitment", "modulus_bits"],
                "properties": _PUZZLE_SCHEMA["properties"],
            },
            # ── Cost controls (oracle_core.tiers) ────────────────────────────────
            # The most expensive call in the family. Measured: T=1M → 7.3 s, T=2M →
            # 14.5 s (exactly linear), so MAX_T=5M is ~36 s of un-parallelisable CPU.
            # `modulus_bits` is a SECOND, independent cost knob — fresh prime generation
            # at 2048 bits is 0.26-1.0 s, at the 3072 maximum it is 2.1-3.4 s — so a
            # ceiling on T alone would leave a third of the cost unbounded.
            #
            # Both ceilings are the schema's own defaults: an unpaid caller who sends
            # neither field is never refused, and gets a fully working time-lock puzzle.
            free_tier_max={"T": 1_000_000, "modulus_bits": 2048},
            # Two terms, because there are two costs. Squarings: ~137 per ms (7.3 s at
            # T=1M, 14.5 s at 2M — exactly linear). Fresh modulus: ~600 ms at 2048 bits,
            # ~2700 ms at 3072, and prime search is probabilistic, so the constants are
            # the observed medians rather than a tight bound.
            cost_ms=_seal_cost_ms,
            # 20 s of CPU per minute per client = a third of a core: two seals at the
            # default T, or many dozens at the small T a test suite uses. The flat
            # 2-calls-per-minute this replaced refused Aestus's own tests on the fourth
            # request while permitting 72 s of CPU a minute — wrong in both directions.
            cpu_budget_ms_per_min=20_000,
            # One core in aggregate for sealing.
            global_cpu_budget_ms_per_min=60_000,
            price_per_call_usd=0.006,
            # HONEST latency: a seal at the default T=1_000_000 does 1M *sequential*
            # squarings mod a 2048-bit N (~140k sq/s in pure Python ⇒ ~7.1s) plus
            # fresh 2048-bit modulus generation (~0.7s). This is a delay-enforcing
            # primitive by design — advertising ~80ms would be a ~100x lie. Latency
            # scales linearly with the caller's T.
            p50_latency_ms=8000,
            success_rate_30d=0.999,
        ),
        Capability(
            capability_id="aestus.open@v1",
            product_id="prod-aestus",
            description=(
                "Open a time-lock puzzle: redo the T sequential squarings to "
                "recover b = a^(2^T) mod N, derive the key, decrypt, and check b "
                "against the puzzle's key_commitment. Anyone can call this once "
                "enough time has elapsed — no trapdoor needed. Costs T squarings."
            ),
            handler=_open,
            input_schema={
                "type": "object",
                "required": ["puzzle"],
                "properties": {"puzzle": _PUZZLE_SCHEMA},
            },
            output_schema={
                "type": "object",
                "required": ["data", "b", "valid"],
                "properties": {
                    "data": {"type": "string"},
                    "b": {"type": "string", "description": "Recovered unlock value a^(2^T) mod N."},
                    "valid": {"type": "boolean", "description": "True iff b matches the key_commitment."},
                },
            },
            # ── Cost controls (oracle_core.tiers) ────────────────────────────────
            # Opening redoes the seal's work, so the ceiling has to match — but T lives
            # INSIDE the caller-supplied puzzle, hence the dotted path. Without it, seal
            # would be bounded and the identical 36 seconds would stay wide open one
            # endpoint over, reachable with a hand-written puzzle that never went
            # through seal at all.
            #
            # Consequence worth stating: a puzzle sealed at a paid T cannot be opened for
            # free. That is the same work either way, so it is consistent rather than
            # awkward — and `aestus.verify@v1` stays free and unbounded (one hash), so
            # whoever does open a large puzzle can publish b and let everyone else
            # confirm the unlock for nothing.
            #
            # `puzzle.modulus_bits` is deliberately NOT bounded: it is caller-declared
            # metadata, while the real cost follows the bit length of N itself. Bounding
            # the label rather than the thing would be theatre — so the THING is bounded,
            # in rsw._parse_puzzle (MAX_MODULUS_BITS), and the cost below scales with the
            # real width. Keying the budget on T alone let a caller sit at the free T
            # ceiling with a 14,000-bit N and buy ~30x the charged work.
            free_tier_max={"puzzle.T": 1_000_000},
            # Same squaring rate as sealing (it is literally the same work), minus the
            # modulus generation — nothing is generated when opening. Quadratic in the
            # modulus width, because that is what a modular squaring costs; the 2048-bit
            # baseline is the rate the 1/137.0 divisor was measured at.
            cost_ms=lambda d: (
                _int_or(_nested(d, "puzzle", "T"), 1) / 137.0
            ) * _modulus_cost_factor(d),
            cpu_budget_ms_per_min=20_000,
            global_cpu_budget_ms_per_min=60_000,
            price_per_call_usd=0.01,
            # HONEST latency: opening redoes the SAME T squarings as sealing
            # (seal-work == open-work, since φ is burned). At the default
            # T=1_000_000 over a 2048-bit N that is ~7.1s of sequential work; no
            # modulus generation here, so it is slightly cheaper than seal. Scales
            # linearly with the puzzle's T.
            p50_latency_ms=7100,
            success_rate_30d=0.999,
        ),
        Capability(
            capability_id="aestus.verify@v1",
            product_id="prod-aestus",
            description=(
                "Cheap, trustless check that a claimed unlock value b is the correct "
                "result of the squarings: SHA256-commitment(b) == puzzle "
                "key_commitment, in ~one hash. Lets a worker who already opened the "
                "puzzle publish b so others confirm the unlock without redoing T "
                "squarings."
            ),
            handler=_verify,
            input_schema={
                "type": "object",
                "required": ["puzzle", "b"],
                "properties": {
                    "puzzle": _PUZZLE_SCHEMA,
                    "b": {"type": "string", "description": "Claimed result of the squarings (a^(2^T) mod N)."},
                },
            },
            output_schema={"type": "object", "required": ["valid"], "properties": {"valid": {"type": "boolean"}}},
            price_per_call_usd=0.001,
            p50_latency_ms=6,
            success_rate_30d=0.999,
        ),
    ],
)
