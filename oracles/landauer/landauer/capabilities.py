"""Landauer oracle spec — thermodynamic compute-cost audit capabilities."""

from __future__ import annotations

import os
from typing import Any

from oracle_core import Capability, OracleSpec

from landauer import thermo


def _audit(d: dict[str, Any]) -> dict[str, Any]:
    ops = d.get("ops")
    if ops is None:
        raise ValueError("missing 'ops' (the operation DAG)")
    return thermo.audit(
        ops=ops,
        temperature_k=float(d.get("temperature_k", 300.0)),
    )


def _verify(d: dict[str, Any]) -> dict[str, Any]:
    ops = d.get("ops")
    if ops is None:
        raise ValueError("missing 'ops' (the operation DAG)")
    return thermo.verify(
        ops=ops,
        irreversible_bits=(int(d["irreversible_bits"]) if d.get("irreversible_bits") is not None else None),
        energy_floor_j=(float(d["energy_floor_j"]) if d.get("energy_floor_j") is not None else None),
        temperature_k=float(d.get("temperature_k", 300.0)),
    )


_OPS_SCHEMA = {
    "ops": {
        "type": "array",
        "description": (
            "The operation DAG. Each element is a gate node "
            "{id, gate, inputs:[id,...], width?}. 'inputs' are the ids of the nodes "
            "this gate reads (its data dependencies / fan-in). Reversible gates "
            "(not, copy/fanout, swap, cnot, toffoli, fredkin, input, output) erase 0 "
            "bits; boolean reductions (and, or, nand, mux, add, ...) erase fan_in-1 "
            "bits; width-erasers (erase, reset, measure, ...) erase 'width' bits."
        ),
        "items": {
            "type": "object",
            "required": ["id", "gate"],
            "properties": {
                "id": {"type": ["string", "integer"], "description": "Unique node id."},
                "gate": {"type": "string", "description": "Gate type (case-insensitive)."},
                "inputs": {
                    "type": "array",
                    "description": "Ids of predecessor nodes (data dependencies).",
                    "items": {"type": ["string", "integer"]},
                },
                "width": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": thermo.MAX_WIDTH,
                    "description": "Bit-width for width-erasers / register sources.",
                },
            },
        },
    },
    "temperature_k": {
        "type": "number",
        "minimum": thermo.MIN_TEMP_K,
        "maximum": thermo.MAX_TEMP_K,
        "default": 300.0,
        "description": "Environment temperature in kelvin (sets the kT·ln2 bit cost).",
    },
}

_HOT_GATES_SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "id": {"type": "string"},
            "gate": {"type": "string"},
            "erased_bits": {"type": "integer"},
        },
    },
}


SPEC = OracleSpec(
    name="Landauer Thermodynamic Compute-Cost Oracle",
    product_id="prod-landauer",
    description=(
        "Thermodynamic cost audit of a computation by Landauer's principle. Given an "
        "operation DAG (gates with fan-in/fan-out), it counts the logically-irreversible "
        "bit-erasures, derives the energy FLOOR in joules (erasures · k_B·T·ln2, T "
        "configurable, default 300 K), computes the Bennett reversible lower bound "
        "(necessary vs wasteful erasures) and a 0..1 thermodynamic efficiency. "
        "Deterministic and replayable: the erasure count is an integer recomputed "
        "bit-for-bit from a SHA-256 circuit_commitment — a proof about the geometry of "
        "information, not a hardware measurement. It audits irreversible energetics; it "
        "neither optimizes nor checks correctness."
    ),
    public_url=os.environ.get("LANDAUER_PUBLIC_URL", "http://localhost:9309"),
    categories=["thermodynamics", "energy", "compute-cost", "reversible-computing", "agent-tooling"],
    signing_key_path=os.environ.get("LANDAUER_SIGNING_KEY", "data/landauer_signing_key"),
    related=["https://github.com/alexar76"],
    capabilities=[
        Capability(
            capability_id="landauer.audit@v1",
            product_id="prod-landauer",
            description=(
                "Audit a computation's thermodynamic cost. Topologically traverses the "
                "op-DAG, counts logically-irreversible bit-erasures per gate (lossy "
                "fan-in / explicit erase), and returns: irreversible_bits, energy_floor_j "
                "(irreversible_bits · k_B·T·ln2), the Bennett reversible lower bound "
                "(reversible_bits) and the avoidable wasteful_bits, a 0..1 efficiency, the "
                "per-gate hot-spot list, and a circuit_commitment for trustless replay."
            ),
            handler=_audit,
            input_schema={
                "type": "object",
                "required": ["ops"],
                "properties": dict(_OPS_SCHEMA),
            },
            output_schema={
                "type": "object",
                "required": ["irreversible_bits", "energy_floor_j", "circuit_commitment"],
                "properties": {
                    "n_ops": {"type": "integer"},
                    "n_edges": {"type": "integer"},
                    "temperature_k": {"type": "number"},
                    "irreversible_bits": {"type": "integer"},
                    "reversible_bits": {"type": "integer"},
                    "wasteful_bits": {"type": "integer"},
                    "energy_floor_j": {"type": "number"},
                    "reversible_floor_j": {"type": "number"},
                    "bit_cost_j": {"type": "number"},
                    "efficiency": {"type": "number"},
                    "circuit_commitment": {"type": "string"},
                    "hot_gates": _HOT_GATES_SCHEMA,
                },
            },
            price_per_call_usd=0.01,
            p50_latency_ms=45,
            success_rate_30d=0.999,
        ),
        Capability(
            capability_id="landauer.verify@v1",
            product_id="prod-landauer",
            description=(
                "Trustless verification: re-derive the canonical circuit, replay the "
                "topological erasure count, recompute the energy floor, and check the "
                "claimed irreversible_bits and/or energy_floor_j bit-for-bit. Cheap; needs "
                "no trust in the oracle. Supply at least one of the two claims."
            ),
            handler=_verify,
            input_schema={
                "type": "object",
                "required": ["ops"],
                "properties": {
                    **_OPS_SCHEMA,
                    "irreversible_bits": {
                        "type": "integer",
                        "minimum": 0,
                        "description": "Claimed irreversible bit-erasure count to check.",
                    },
                    "energy_floor_j": {
                        "type": "number",
                        "minimum": 0,
                        "description": "Claimed Landauer energy floor in joules to check.",
                    },
                },
            },
            output_schema={
                "type": "object",
                "required": ["valid", "circuit_commitment", "recomputed_irreversible_bits", "energy_floor_j"],
                "properties": {
                    "valid": {"type": "boolean"},
                    "temperature_k": {"type": "number"},
                    "circuit_commitment": {"type": "string"},
                    "recomputed_irreversible_bits": {"type": "integer"},
                    "energy_floor_j": {"type": "number"},
                    "claimed_irreversible_bits": {"type": "integer"},
                    "claimed_energy_floor_j": {"type": "number"},
                    "bits_match": {"type": "boolean"},
                    "energy_match": {"type": "boolean"},
                },
            },
            price_per_call_usd=0.001,
            p50_latency_ms=18,
            success_rate_30d=0.999,
        ),
    ],
)
