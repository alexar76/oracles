"""Feed every producer's own output straight back into its verifier.

This is the test nobody had written, and both serious defects found in the 2026-07-28
audit lived exactly in the seam it covers — between two halves of one oracle, each of
which had passing tests of its own:

  chronos  verify accepted g=0, for which π^l·g^r ≡ y is an identity, so a proof of a
           million sequential squarings verified having cost nothing.
  sortes   draw emitted `alpha` as bare hex, verify UTF-8 encoded it, and every honest
           proof the oracle issued verified as false.

Neither is visible from inside one half. A producer test asserts the output is correct;
a verifier test asserts a hand-built input verifies. Only composing them asks the
question a buyer asks: *does the thing I was sold check out?*

WIRING is deliberately explicit rather than clever. Where a verifier wants a field under
a different name (`fourier`: fiedler_value → lambda) or nested (`percola`: f_c lives under
the attack strategy) or produced by a third capability (`aestus`: `b` comes from open, not
seal), that mapping IS the knowledge a caller needs and the thing that silently drifts.
Writing it out means a rename breaks this file instead of breaking the marketplace.
"""

from __future__ import annotations

import pytest

from oracle_family_app.main import build_family_spec

GRAPH = {"edges": [[0, 1, 1.0], [1, 2, 2.0], [2, 0, 1.5], [0, 3, 2.0], [3, 1, 1.0]]}


def _aestus_verify_input(out, inp, call):
    # The claimed result of the squarings comes from open(), not seal() — seal alone has
    # nothing to verify against, which is the point of a time-lock puzzle.
    return {"puzzle": out, "b": call("aestus.open@v1", {"puzzle": out})["b"]}


# (producer, producer input, verifier, producer output -> verifier input)
PAIRS = [
    ("chronos.eval@v1", {"seed": "rt", "difficulty": 300}, "chronos.verify@v1",
     lambda o, i, c: {"g": o["g"], "y": o["y"], "difficulty": o["difficulty"], "proof": o["proof"]}),
    ("sortes.draw@v1", {"alpha": "rt"}, "sortes.verify@v1",
     lambda o, i, c: {"public_key": o["public_key"], "alpha": o["alpha"], "pi": o["pi"]}),
    ("lumen.reputation@v1", {"nodes": 4, "edges": GRAPH["edges"]}, "lumen.verify@v1",
     lambda o, i, c: {"nodes": i["nodes"], "edges": i["edges"], "scores": o["scores"],
                      "graph_commitment": o.get("graph_commitment")}),
    ("percola.threshold@v1", dict(GRAPH), "percola.verify@v1",
     lambda o, i, c: {**i, "f_c": o["targeted"]["f_c"], "attack": "targeted"}),
    ("fermat.route@v1", {**GRAPH, "start": 0, "goal": 2}, "fermat.verify@v1",
     lambda o, i, c: {**i, "path": o["path"], "potentials": o["potentials"], "total": o["total"]}),
    ("ablation.cascade@v1", dict(GRAPH), "ablation.verify@v1",
     lambda o, i, c: {**i, "claimed_tau": o.get("tau"), "grains": o.get("grains", 4000)}),
    ("kantor.transport@v1", {"a": [0.5, 0.5], "b": [0.3, 0.7], "cost": [[0, 1], [1, 0]]},
     "kantor.verify@v1",
     lambda o, i, c: {**i, "plan": o["plan"], "potentials": o["potentials"], "claimed_cost": o["cost"]}),
    ("fourier.spectrum@v1", dict(GRAPH), "fourier.verify@v1",
     lambda o, i, c: {**i, "fiedler_value": o["fiedler_value"], "fiedler_vector": o["fiedler_vector"]}),
    ("gauss.field@v1", {"X": [[0.0], [1.0], [2.0]], "y": [0.0, 1.0, 4.0], "query": [[0.5]]},
     "gauss.verify@v1",
     lambda o, i, c: {**i, "claimed_mean": o.get("mean"), "claimed_var": o.get("var")}),
    ("aestus.seal@v1", {"data": "hello", "T": 1500}, "aestus.verify@v1", _aestus_verify_input),
    ("landauer.audit@v1",
     {"ops": [{"id": "a", "gate": "AND", "inputs": []}, {"id": "b", "gate": "NOT", "inputs": ["a"]}]},
     "landauer.verify@v1",
     lambda o, i, c: {**i, "irreversible_bits": o.get("irreversible_bits"),
                      "energy_floor_j": o.get("energy_floor_j")}),
]


@pytest.fixture(scope="module")
def call():
    """Invoke a family capability by id, through the same handlers the service uses."""
    caps = {c.capability_id: c for c in build_family_spec().capabilities}

    def _call(cap_id, payload):
        cap = caps.get(cap_id)
        if cap is None:
            pytest.skip(f"{cap_id} not installed in this environment")
        return cap.handler(payload)

    return _call


@pytest.mark.parametrize("producer,pin,verifier,wire", PAIRS, ids=[p[0] for p in PAIRS])
def test_a_verifier_accepts_its_own_producers_output(producer, pin, verifier, wire, call):
    out = call(producer, dict(pin))
    result = call(verifier, wire(out, dict(pin), call))
    assert result.get("valid") is True, (
        f"{verifier} rejected what {producer} just produced: {str(result)[:200]}"
    )


def test_chronos_still_refuses_a_degenerate_generator(call):
    """The specific forgery that verified in production: g=0 makes the check an identity."""
    from chronos import vdf

    T = 1_000_000
    out = call("chronos.verify@v1",
               {"g": "0", "y": "0", "difficulty": T,
                "proof": {"pi": "0", "l": str(vdf.hash_to_prime(0, 0, T))}})
    assert out["valid"] is False, "a proof of a million squarings verified with no work"


def test_sortes_rejects_a_seed_it_did_not_sign(call):
    """The round-trip above passes trivially if the verifier says yes to everything."""
    d = call("sortes.draw@v1", {"alpha": "rt"})
    out = call("sortes.verify@v1",
               {"public_key": d["public_key"], "alpha": "hex:00", "pi": d["pi"]})
    assert out["valid"] is False
