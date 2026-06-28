"""Landauer — a thermodynamic compute-cost audit with a deterministic, replayable proof.

LANDAUER answers a question no benchmark and no price quote can: not how *fast* a
computation runs nor whether its *answer* is correct, but the **thermodynamic lower
bound** on the energy any physical machine must dissipate to perform it. By Landauer's
principle, erasing one bit of information in an environment at temperature ``T`` costs
at least

    E_min = k_B · T · ln 2     (≈ 2.85 zJ at T = 300 K),

because erasure is logically irreversible: it collapses two distinguishable input
states onto one output state, and the lost phase-space volume must be paid for as heat
(``ΔS_environment ≥ k_B ln 2``). Logically *reversible* operations (NOT, COPY/fan-out,
and the universal reversible gates Toffoli/CCNOT and Fredkin/CSWAP) preserve
distinguishability and carry **no** Landauer floor; only the *information destroyed*
by a circuit is thermodynamically expensive (Bennett, 1973; Landauer, 1961).

This module turns that principle into an exact, recomputable accounting over an
operation DAG. It is a *proof about the geometry of information*, not a hardware
measurement — it bounds what physics permits, not what a given chip achieves.

Everything here is exact and replayable — no heuristics, no oracle-controlled RNG:

1. **Canonicalisation.** The op-DAG is normalised (nodes sorted by id, edges sorted,
   gate types lower-cased) and hashed to a ``circuit_commitment`` (SHA-256). The whole
   audit is a pure function of that committed circuit.
2. **Per-gate erasure count.** Each gate's irreversible bit-loss is read from a small,
   physically-grounded gate table as ``log2`` of the collapse in distinguishable
   states — e.g. a 2-input AND maps 4 input states onto 2 (output, surviving copy),
   destroying ``log2(4/2) = 1`` bit; a generic ``k``-input boolean reduction destroys
   ``k - 1`` bits; an explicit ``erase`` of a ``w``-bit register destroys ``w`` bits.
   Reversible gates destroy ``0`` bits.
3. **Topological pass.** The DAG is traversed once in topological order (so the audit
   also certifies acyclicity), summing erased bits to an **integer** total —
   recomputable bit-for-bit by any verifier.
4. **Reversible lower bound.** A Bennett-style resynthesis count gives the *necessary*
   floor: even an optimally reversible implementation must finally erase the circuit's
   net information loss between its declared inputs and its declared outputs. The gap
   between the actual erasures and that necessary floor is **wasteful** dissipation
   that reversible computing could recover.

The ``verify`` capability replays the topological count and re-derives the energy
floor, checking a claimed ``irreversible_bits`` or ``energy_floor_j`` bit-for-bit.
The bound is **proven by recomputation, not asserted on trust.**
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any

# Boltzmann constant (CODATA, exact since the 2019 SI redefinition), in J/K.
K_B = 1.380649e-23
LN2 = math.log(2.0)

# Guards against pathological payloads (the audit is O(V + E) but bound it anyway).
MAX_NODES = 20000
MAX_EDGES = 80000
MAX_WIDTH = 4096            # max bit-width an explicit erase / register may declare
MAX_FANIN = 256             # max inputs to a single reduction gate
MIN_TEMP_K = 1e-3           # below this the floor is meaningless / numerically unstable
MAX_TEMP_K = 1e6

# --- Gate table -------------------------------------------------------------------
# Each entry says how many bits a gate of the given type *irreversibly erases*, as a
# function of its fan-in k (number of incoming data edges) and an optional declared
# bit-width w. The count is log2 of the collapse in distinguishable states.
#
# Reversible gates (the right-hand set) are bijections on their state space — they
# permute inputs to outputs without losing any distinguishable state, so they carry
# NO Landauer floor regardless of fan-in.

# Logically reversible gates: a permutation of states, zero erasure.
REVERSIBLE = {
    "id", "identity", "wire", "buffer",
    "not", "inv", "negate",
    "copy", "fanout", "fan_out", "split", "delay",
    "swap", "cswap", "fredkin",
    "cnot", "xor2", "ccnot", "toffoli",
    "perm", "permute", "rotate", "reverse",
    "input", "in", "source",        # declares a primary input wire (no op)
    "output", "out", "sink",        # declares a primary output wire (no op)
}

# Logically irreversible boolean reductions: a k-input gate keeps one output bit and
# destroys the other k-1 input bits' worth of distinguishability. (For k inputs the
# truth table has 2^k rows but the gate exposes only its output, so the recoverable
# state space shrinks by a factor 2^(k-1).)
REDUCTIONS = {
    "and", "nand", "or", "nor", "xnor",
    "maj", "majority", "mux", "select",
    "add", "sum", "reduce", "merge", "join", "min", "max",
    "and3", "or3",
}

# Operations whose erasure is exactly their declared bit-width w (a full overwrite of
# a register with a constant / reset / measurement collapse).
WIDTH_ERASERS = {
    "erase", "reset", "clear", "zero", "set", "overwrite",
    "discard", "drop", "free", "deallocate", "measure", "collapse",
}


def _gate_erased_bits(gate: str, fan_in: int, width: int | None) -> int:
    """Bits irreversibly erased by one gate.

    - reversible gate                       → 0
    - width-eraser (erase/reset/measure …)  → declared width w (default 1)
    - boolean reduction with fan-in k       → max(k - 1, 0)
    - unknown gate                          → treated as a worst-case k-input reduction
                                              (k-1 bits) so audits fail *safe* (over-
                                              counting cost rather than hiding it).
    """
    g = gate.strip().lower()
    if g in REVERSIBLE:
        return 0
    if g in WIDTH_ERASERS:
        w = 1 if width is None else int(width)
        if w < 0:
            raise ValueError(f"gate '{gate}' has negative width {w}")
        if w > MAX_WIDTH:
            raise ValueError(f"gate '{gate}' width {w} exceeds MAX_WIDTH={MAX_WIDTH}")
        return w
    # reductions and unknown gates collapse k inputs to 1 output → k-1 erased bits.
    k = fan_in
    if g in REDUCTIONS or True:  # unknown ⇒ conservative reduction model
        return max(k - 1, 0)


def canonical_circuit(
    ops: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, int], list[tuple[int, int]], str]:
    """Normalise an op-DAG to a canonical, hashable form.

    ``ops`` is a list of node dicts, each:
        {"id": <str|int>, "gate": <str>, "inputs": [<id>,...], "width"?: <int>}
    A node's fan-in is ``len(inputs)`` (data dependencies); edges are derived from
    ``inputs`` (predecessor → node). Returns
    ``(nodes, index, edges, commitment)`` where ``nodes`` is the canonical node list
    (sorted by id, gate lower-cased), ``index`` maps id→position, ``edges`` are the
    sorted unique (src_idx, dst_idx) pairs, and ``commitment`` is the SHA-256 of the
    canonical JSON.
    """
    if not isinstance(ops, list) or not ops:
        raise ValueError("circuit must be a non-empty list of ops")
    if len(ops) > MAX_NODES:
        raise ValueError(f"too many nodes (max {MAX_NODES})")

    # First pass: collect ids, detect duplicates, normalise gate + width.
    raw: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for i, op in enumerate(ops):
        if not isinstance(op, dict):
            raise ValueError(f"op #{i} is not an object")
        if "id" not in op:
            raise ValueError(f"op #{i} is missing 'id'")
        nid = str(op["id"])
        if nid in seen_ids:
            raise ValueError(f"duplicate node id '{nid}'")
        seen_ids.add(nid)
        gate = str(op.get("gate", "")).strip().lower()
        if not gate:
            raise ValueError(f"op '{nid}' is missing 'gate'")
        inputs_raw = op.get("inputs", []) or []
        if not isinstance(inputs_raw, (list, tuple)):
            raise ValueError(f"op '{nid}' inputs must be a list")
        inputs = [str(x) for x in inputs_raw]
        if len(inputs) > MAX_FANIN:
            raise ValueError(f"op '{nid}' fan-in {len(inputs)} exceeds MAX_FANIN={MAX_FANIN}")
        width = op.get("width")
        node = {"id": nid, "gate": gate, "inputs": inputs}
        if width is not None:
            node["width"] = int(width)
        raw.append(node)

    # Validate that every referenced input exists.
    for node in raw:
        for src in node["inputs"]:
            if src not in seen_ids:
                raise ValueError(f"op '{node['id']}' references unknown input '{src}'")

    # Canonical node order: sorted by id (string order is stable + reproducible).
    nodes = sorted(raw, key=lambda d: d["id"])
    index = {n["id"]: i for i, n in enumerate(nodes)}

    edge_set = sorted({(index[src], index[n["id"]]) for n in nodes for src in n["inputs"]})
    if len(edge_set) > MAX_EDGES:
        raise ValueError(f"too many edges (max {MAX_EDGES})")

    canon = {
        "nodes": [
            {"id": n["id"], "gate": n["gate"], "inputs": sorted(n["inputs"]),
             **({"width": n["width"]} if "width" in n else {})}
            for n in nodes
        ]
    }
    commitment = hashlib.sha256(
        json.dumps(canon, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()
    return nodes, index, edge_set, commitment


def topo_order(nodes: list[dict[str, Any]], index: dict[str, int], edges: list[tuple[int, int]]) -> list[int]:
    """Deterministic Kahn topological order; raises on a cycle.

    Ties are broken by node index (i.e. by canonical id order), so the order is a pure
    function of the committed circuit and any verifier reproduces it exactly.
    """
    n = len(nodes)
    indeg = [0] * n
    succ: list[list[int]] = [[] for _ in range(n)]
    for s, d in edges:
        indeg[d] += 1
        succ[s].append(d)
    for lst in succ:
        lst.sort()
    # Min-ordered ready set without importing heapq: small graphs, linear scans are fine
    # for determinism clarity; for larger graphs we keep a sorted ready list.
    ready = sorted(i for i in range(n) if indeg[i] == 0)
    order: list[int] = []
    while ready:
        u = ready.pop(0)
        order.append(u)
        inserted = False
        for v in succ[u]:
            indeg[v] -= 1
            if indeg[v] == 0:
                # insert v keeping `ready` sorted
                lo, hi = 0, len(ready)
                while lo < hi:
                    mid = (lo + hi) // 2
                    if ready[mid] < v:
                        lo = mid + 1
                    else:
                        hi = mid
                ready.insert(lo, v)
                inserted = True
        _ = inserted
    if len(order) != n:
        raise ValueError("circuit is not a DAG (cycle detected)")
    return order


def energy_floor_j(bits: int, temperature_k: float) -> float:
    """Landauer floor in joules for ``bits`` irreversible erasures at temperature T."""
    return bits * K_B * temperature_k * LN2


def _clamp_temp(temperature_k: float) -> float:
    t = float(temperature_k)
    if not math.isfinite(t):
        raise ValueError("temperature must be finite")
    if t < MIN_TEMP_K:
        raise ValueError(f"temperature {t} K below MIN_TEMP_K={MIN_TEMP_K}")
    if t > MAX_TEMP_K:
        raise ValueError(f"temperature {t} K above MAX_TEMP_K={MAX_TEMP_K}")
    return t


def _count_irreversible(nodes: list[dict[str, Any]], order: list[int]) -> tuple[int, list[dict[str, Any]]]:
    """Topological pass: total irreversible bits + per-gate breakdown."""
    total = 0
    per_gate: list[dict[str, Any]] = []
    for idx in order:
        n = nodes[idx]
        erased = _gate_erased_bits(n["gate"], len(n["inputs"]), n.get("width"))
        total += erased
        if erased > 0:
            per_gate.append({"id": n["id"], "gate": n["gate"], "erased_bits": erased})
    return total, per_gate


def _reversible_floor_bits(nodes: list[dict[str, Any]], index: dict[str, int], edges: list[tuple[int, int]]) -> int:
    """Bennett-style *necessary* erasure floor.

    A reversible implementation can run any logic without erasing intermediates, but it
    must finally discard the circuit's net information loss: the difference between the
    bits that *enter* (primary input wires) and the bits that *survive as declared
    outputs*. We model the necessary floor as

        reversible_floor = max(0, primary_input_bits - primary_output_bits)

    where a primary input is a node with zero fan-in that is consumed by something
    (a real source of distinguishable state) and a primary output is a node nothing
    consumes (a sink the computation is required to preserve). This is the minimum any
    machine — reversible or not — must erase to map that many input states onto that
    many output states. Width-erasers and explicit ``output``/``sink`` declarations are
    honoured.
    """
    n = len(nodes)
    out_deg = [0] * n
    for s, _d in edges:
        out_deg[s] += 1

    # Bit-width of a wire: an explicit width on a source/erase node, else 1 bit.
    def wire_bits(node: dict[str, Any]) -> int:
        w = node.get("width")
        return int(w) if w is not None else 1

    input_bits = 0
    output_bits = 0
    for i, node in enumerate(nodes):
        gate = node["gate"]
        fanin = len(node["inputs"])
        # Primary input: a node with no data dependencies that feeds something, OR an
        # explicit input/source declaration. It injects distinguishable state.
        is_source = gate in ("input", "in", "source") or (fanin == 0 and gate not in WIDTH_ERASERS)
        if is_source and out_deg[i] > 0:
            input_bits += wire_bits(node)
        # Primary output: a node nothing consumes, OR an explicit output/sink. The
        # computation must preserve its state, so it does NOT count toward erasure.
        is_sink = gate in ("output", "out", "sink") or (out_deg[i] == 0 and gate not in WIDTH_ERASERS)
        if is_sink:
            output_bits += wire_bits(node)

    return max(0, input_bits - output_bits)


def audit(ops: list[dict[str, Any]], temperature_k: float = 300.0) -> dict[str, Any]:
    """Full Landauer audit — the ``landauer.audit@v1`` handler core."""
    t = _clamp_temp(temperature_k)
    nodes, index, edges, commitment = canonical_circuit(ops)
    order = topo_order(nodes, index, edges)

    irreversible_bits, per_gate = _count_irreversible(nodes, order)
    reversible_bits = _reversible_floor_bits(nodes, index, edges)
    # The reversible necessary floor can never exceed what the actual circuit erases:
    # if a circuit erases fewer bits than its declared net info loss, the declaration is
    # the binding bound. Clamp so wasteful_bits is always ≥ 0.
    reversible_bits = min(reversible_bits, irreversible_bits)
    wasteful_bits = irreversible_bits - reversible_bits

    floor_j = energy_floor_j(irreversible_bits, t)
    reversible_floor_j = energy_floor_j(reversible_bits, t)

    # Thermodynamic efficiency: how close the circuit's dissipation is to the necessary
    # reversible minimum. 1.0 = already optimal (no wasteful erasure); 0.0 = all of its
    # erasure was avoidable. A circuit that erases nothing is, by convention, perfectly
    # efficient (efficiency = 1.0).
    if irreversible_bits == 0:
        efficiency = 1.0
    else:
        efficiency = reversible_bits / irreversible_bits

    return {
        "n_ops": len(nodes),
        "n_edges": len(edges),
        "temperature_k": t,
        "irreversible_bits": irreversible_bits,
        "reversible_bits": reversible_bits,
        "wasteful_bits": wasteful_bits,
        "energy_floor_j": floor_j,
        "reversible_floor_j": reversible_floor_j,
        "bit_cost_j": K_B * t * LN2,
        "efficiency": round(efficiency, 6),
        "circuit_commitment": commitment,
        "hot_gates": per_gate[:64],  # the irreversible gates, capped for payload size
        "note": (
            "energy_floor_j = irreversible_bits · k_B · T · ln2 (Landauer floor); "
            "reversible_bits is the Bennett necessary minimum; efficiency = "
            "reversible_bits / irreversible_bits. Recomputable from circuit_commitment."
        ),
    }


def verify(
    ops: list[dict[str, Any]],
    irreversible_bits: int | None = None,
    energy_floor_j: float | None = None,
    temperature_k: float = 300.0,
) -> dict[str, Any]:
    """Trustless re-computation — the ``landauer.verify@v1`` handler core.

    Re-derives the canonical circuit, replays the topological erasure count, recomputes
    the energy floor, and checks the claimed ``irreversible_bits`` and/or
    ``energy_floor_j``. At least one of the two claims must be supplied.
    """
    if irreversible_bits is None and energy_floor_j is None:
        raise ValueError("supply at least one of 'irreversible_bits' or 'energy_floor_j' to verify")

    t = _clamp_temp(temperature_k)
    nodes, index, edges, commitment = canonical_circuit(ops)
    order = topo_order(nodes, index, edges)
    recomputed_bits, _per_gate = _count_irreversible(nodes, order)
    recomputed_floor = energy_floor_j_fn(recomputed_bits, t)

    bits_ok = irreversible_bits is None or int(irreversible_bits) == recomputed_bits
    # Energy comparison is in physical units; use a relative tolerance to absorb float
    # round-trips through JSON. One bit at 300 K is ~2.85e-21 J, so we compare with a
    # tolerance of half a bit's worth of energy (cannot ambiguate adjacent integers).
    if energy_floor_j is None:
        energy_ok = True
    else:
        half_bit = 0.5 * K_B * t * LN2
        energy_ok = abs(float(energy_floor_j) - recomputed_floor) <= half_bit

    return {
        "valid": bool(bits_ok and energy_ok),
        "temperature_k": t,
        "circuit_commitment": commitment,
        "recomputed_irreversible_bits": recomputed_bits,
        "energy_floor_j": recomputed_floor,
        "claimed_irreversible_bits": (None if irreversible_bits is None else int(irreversible_bits)),
        "claimed_energy_floor_j": (None if energy_floor_j is None else float(energy_floor_j)),
        "bits_match": bool(bits_ok),
        "energy_match": bool(energy_ok),
    }


# Alias kept readable inside verify() above without shadowing the module-level name used
# elsewhere; both refer to the same pure function.
energy_floor_j_fn = energy_floor_j
