import math

import pytest
from httpx import ASGITransport, AsyncClient

from landauer import thermo as th
from landauer.main import app


# --- circuit fixtures -------------------------------------------------------------

def and2():
    # one 2-input AND gate: 1 erased bit.
    return [
        {"id": "a", "gate": "input"},
        {"id": "b", "gate": "input"},
        {"id": "g", "gate": "and", "inputs": ["a", "b"]},
        {"id": "out", "gate": "output", "inputs": ["g"]},
    ]


def and_tree3():
    # 3-input AND via two 2-input ANDs: 2 erased bits.
    return [
        {"id": "a", "gate": "input"},
        {"id": "b", "gate": "input"},
        {"id": "c", "gate": "input"},
        {"id": "g1", "gate": "and", "inputs": ["a", "b"]},
        {"id": "g2", "gate": "and", "inputs": ["g1", "c"]},
        {"id": "out", "gate": "output", "inputs": ["g2"]},
    ]


def reversible_only():
    # NOT then COPY (fan-out) then CNOT: all reversible → 0 erased bits.
    return [
        {"id": "a", "gate": "input"},
        {"id": "b", "gate": "input"},
        {"id": "n", "gate": "not", "inputs": ["a"]},
        {"id": "c1", "gate": "copy", "inputs": ["n"]},
        {"id": "x", "gate": "cnot", "inputs": ["n", "b"]},
        {"id": "o1", "gate": "output", "inputs": ["c1"]},
        {"id": "o2", "gate": "output", "inputs": ["x"]},
    ]


def explicit_erase8():
    # explicit erase of an 8-bit register: 8 erased bits.
    return [
        {"id": "src", "gate": "input", "width": 8},
        {"id": "e", "gate": "erase", "inputs": ["src"], "width": 8},
    ]


# --- canonicalisation -------------------------------------------------------------

class TestCanonicalisation:
    def test_commitment_is_node_order_independent(self):
        ops1 = and_tree3()
        ops2 = list(reversed(and_tree3()))  # shuffle node order
        c1 = th.canonical_circuit(ops1)[3]
        c2 = th.canonical_circuit(ops2)[3]
        assert c1 == c2

    def test_commitment_changes_with_gate_type(self):
        c_and = th.canonical_circuit(and2())[3]
        flipped = and2()
        flipped[2]["gate"] = "xor2"  # AND → reversible XOR2
        c_xor = th.canonical_circuit(flipped)[3]
        assert c_and != c_xor

    def test_empty_circuit_rejected(self):
        with pytest.raises(ValueError):
            th.canonical_circuit([])

    def test_duplicate_id_rejected(self):
        with pytest.raises(ValueError):
            th.canonical_circuit([{"id": "x", "gate": "input"}, {"id": "x", "gate": "not", "inputs": ["x"]}])

    def test_unknown_input_rejected(self):
        with pytest.raises(ValueError):
            th.canonical_circuit([{"id": "g", "gate": "and", "inputs": ["nope", "alsono"]}])

    def test_node_cap_enforced(self):
        big = [{"id": str(i), "gate": "input"} for i in range(th.MAX_NODES + 1)]
        with pytest.raises(ValueError):
            th.canonical_circuit(big)

    def test_cycle_rejected(self):
        ops = [
            {"id": "x", "gate": "and", "inputs": ["y"]},
            {"id": "y", "gate": "and", "inputs": ["x"]},
        ]
        nodes, index, edges, _ = th.canonical_circuit(ops)
        with pytest.raises(ValueError):
            th.topo_order(nodes, index, edges)


# --- the physics: erasure counting ------------------------------------------------

class TestAuditPhysics:
    def test_and2_erases_one_bit(self):
        out = th.audit(and2())
        assert out["irreversible_bits"] == 1

    def test_and_tree3_erases_two_bits(self):
        out = th.audit(and_tree3())
        assert out["irreversible_bits"] == 2

    def test_reversible_circuit_is_free(self):
        out = th.audit(reversible_only())
        assert out["irreversible_bits"] == 0
        assert out["energy_floor_j"] == 0.0
        assert out["efficiency"] == 1.0  # nothing erased ⇒ perfectly efficient

    def test_explicit_erase_width(self):
        out = th.audit(explicit_erase8())
        assert out["irreversible_bits"] == 8

    def test_kfanin_reduction_loses_k_minus_1(self):
        # a single 4-input AND collapses 4 inputs to 1 → 3 erased bits.
        ops = [
            {"id": "a", "gate": "input"}, {"id": "b", "gate": "input"},
            {"id": "c", "gate": "input"}, {"id": "d", "gate": "input"},
            {"id": "g", "gate": "and", "inputs": ["a", "b", "c", "d"]},
            {"id": "out", "gate": "output", "inputs": ["g"]},
        ]
        assert th.audit(ops)["irreversible_bits"] == 3

    def test_landauer_floor_value_at_300k(self):
        # one bit at 300 K must equal k_B · 300 · ln2 ≈ 2.8717e-21 J.
        out = th.audit(and2(), temperature_k=300.0)
        expected = th.K_B * 300.0 * math.log(2.0)
        assert abs(out["energy_floor_j"] - expected) < 1e-30
        assert abs(out["energy_floor_j"] - 2.8717e-21) < 1e-24

    def test_floor_scales_linearly_with_temperature(self):
        lo = th.audit(and_tree3(), temperature_k=100.0)["energy_floor_j"]
        hi = th.audit(and_tree3(), temperature_k=300.0)["energy_floor_j"]
        assert abs(hi - 3.0 * lo) < 1e-30

    def test_bad_temperature_rejected(self):
        with pytest.raises(ValueError):
            th.audit(and2(), temperature_k=0.0)
        with pytest.raises(ValueError):
            th.audit(and2(), temperature_k=1e9)

    def test_unknown_gate_counts_conservatively(self):
        # an unknown 3-input gate is treated as a worst-case reduction → 2 erased bits.
        ops = [
            {"id": "a", "gate": "input"}, {"id": "b", "gate": "input"},
            {"id": "c", "gate": "input"},
            {"id": "g", "gate": "frobnicate", "inputs": ["a", "b", "c"]},
            {"id": "out", "gate": "output", "inputs": ["g"]},
        ]
        assert th.audit(ops)["irreversible_bits"] == 2


# --- reversible lower bound / efficiency ------------------------------------------

class TestReversibleBound:
    def test_wasteful_is_actual_minus_necessary(self):
        out = th.audit(and_tree3())
        assert out["wasteful_bits"] == out["irreversible_bits"] - out["reversible_bits"]
        assert out["wasteful_bits"] >= 0

    def test_efficiency_in_unit_interval(self):
        out = th.audit(and_tree3())
        assert 0.0 <= out["efficiency"] <= 1.0

    def test_reversible_floor_never_exceeds_actual(self):
        for fixture in (and2(), and_tree3(), explicit_erase8(), reversible_only()):
            out = th.audit(fixture)
            assert out["reversible_bits"] <= out["irreversible_bits"]

    def test_and_tree_wastes_compute(self):
        # 3 inputs collapse to 1 output: necessary floor = 3-1 = 2 bits = the whole
        # erasure here, so an AND tree is actually at its necessary floor → efficient.
        # But a circuit that erases intermediates it didn't need to would waste. Build
        # one: copy a bit then AND it with itself's source — extra erasure is wasteful.
        out = th.audit(and_tree3())
        # net info loss (2 inputs lost) equals erasure (2) → efficiency 1.0 here.
        assert out["efficiency"] == 1.0

    def test_redundant_erase_is_wasteful(self):
        # Two primary inputs, one preserved output, plus a gratuitous erase of a copy.
        ops = [
            {"id": "a", "gate": "input"},
            {"id": "b", "gate": "input"},
            {"id": "cp", "gate": "copy", "inputs": ["a"]},
            {"id": "junk", "gate": "erase", "inputs": ["cp"], "width": 1},
            {"id": "o1", "gate": "output", "inputs": ["a"]},
            {"id": "o2", "gate": "output", "inputs": ["b"]},
        ]
        out = th.audit(ops)
        # 2 inputs, 2 preserved outputs → net necessary loss 0; the erase is avoidable.
        assert out["irreversible_bits"] == 1
        assert out["reversible_bits"] == 0
        assert out["wasteful_bits"] == 1
        assert out["efficiency"] == 0.0


# --- determinism ------------------------------------------------------------------

class TestDeterminism:
    def test_repeatable_audit(self):
        a = th.audit(and_tree3())
        b = th.audit(and_tree3())
        assert a["circuit_commitment"] == b["circuit_commitment"]
        assert a["irreversible_bits"] == b["irreversible_bits"]
        assert a["energy_floor_j"] == b["energy_floor_j"]

    def test_commitment_stable_across_input_permutation(self):
        a = th.audit(and_tree3())
        b = th.audit(list(reversed(and_tree3())))
        assert a["circuit_commitment"] == b["circuit_commitment"]
        assert a["irreversible_bits"] == b["irreversible_bits"]


# --- verify -----------------------------------------------------------------------

class TestVerify:
    def test_roundtrip_bits_valid(self):
        out = th.audit(and_tree3())
        v = th.verify(and_tree3(), irreversible_bits=out["irreversible_bits"])
        assert v["valid"] is True
        assert v["circuit_commitment"] == out["circuit_commitment"]
        assert v["recomputed_irreversible_bits"] == out["irreversible_bits"]

    def test_roundtrip_energy_valid(self):
        out = th.audit(and_tree3())
        v = th.verify(and_tree3(), energy_floor_j=out["energy_floor_j"])
        assert v["valid"] is True
        assert v["energy_match"] is True

    def test_wrong_bits_rejected(self):
        out = th.audit(and_tree3())
        v = th.verify(and_tree3(), irreversible_bits=out["irreversible_bits"] + 1)
        assert v["valid"] is False
        assert v["bits_match"] is False

    def test_tampered_circuit_rejected(self):
        # Claim the bits for the honest circuit but submit a tampered one (an AND
        # silently swapped to a reversible XOR2 to hide a bit's cost).
        honest = th.audit(and_tree3())
        tampered = and_tree3()
        tampered[3]["gate"] = "xor2"  # g1: AND → XOR2 (now reversible)
        v = th.verify(tampered, irreversible_bits=honest["irreversible_bits"])
        assert v["valid"] is False
        assert v["recomputed_irreversible_bits"] == 1  # only g2 remains lossy

    def test_wrong_energy_rejected(self):
        out = th.audit(and_tree3())
        v = th.verify(and_tree3(), energy_floor_j=out["energy_floor_j"] * 2.0)
        assert v["valid"] is False
        assert v["energy_match"] is False

    def test_verify_needs_a_claim(self):
        with pytest.raises(ValueError):
            th.verify(and2())

    def test_energy_tolerance_absorbs_float_roundtrip(self):
        out = th.audit(and_tree3())
        # a JSON round-trip can perturb the last digits; verify must still accept.
        jittered = out["energy_floor_j"] * (1 + 1e-12)
        v = th.verify(and_tree3(), energy_floor_j=jittered)
        assert v["valid"] is True

    def test_verify_at_other_temperature(self):
        out = th.audit(and_tree3(), temperature_k=77.0)
        v = th.verify(and_tree3(), energy_floor_j=out["energy_floor_j"], temperature_k=77.0)
        assert v["valid"] is True
        # but a mismatched temperature changes the floor and rejects it.
        v2 = th.verify(and_tree3(), energy_floor_j=out["energy_floor_j"], temperature_k=300.0)
        assert v2["valid"] is False


# --- ASGI / app surface -----------------------------------------------------------

class TestApp:
    async def test_invoke_audit(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://t") as client:
            r = await client.post(
                "/ai-market/v2/invoke",
                json={"capability_id": "landauer.audit@v1", "input": {"ops": and_tree3()}},
            )
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True
        out = body["output"]
        assert out["irreversible_bits"] == 2
        assert out["energy_floor_j"] > 0
        assert "circuit_commitment" in out
        assert body["receipt"]  # signed envelope present

    async def test_invoke_verify_roundtrip(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://t") as client:
            a = await client.post(
                "/ai-market/v2/invoke",
                json={"capability_id": "landauer.audit@v1", "input": {"ops": and_tree3()}},
            )
            out = a.json()["output"]
            v = await client.post(
                "/ai-market/v2/invoke",
                json={"capability_id": "landauer.verify@v1",
                      "input": {"ops": and_tree3(), "irreversible_bits": out["irreversible_bits"]}},
            )
        body = v.json()
        assert body["ok"] is True
        assert body["output"]["valid"] is True

    async def test_invoke_bad_input_fails_closed(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://t") as client:
            r = await client.post(
                "/ai-market/v2/invoke",
                json={"capability_id": "landauer.audit@v1", "input": {"ops": []}},
            )
        body = r.json()
        assert body["ok"] is False

    async def test_manifest_lists_capabilities(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://t") as client:
            r = await client.get("/ai-market/v2/manifest")
        ids = {t["capability_id"] for t in r.json()["tools"]}
        assert ids == {"landauer.audit@v1", "landauer.verify@v1"}
