"""The same checks against every capability of every oracle.

Per-oracle suites had drifted from 14 tests to 40, and counted per capability the spread
was wider still — sortes 20 each, platon 4. Levelling that by hand means writing the same
assertions eighteen times and letting them diverge again. Parametrising over the family
spec makes coverage uniform by construction, and a new oracle inherits all of it the day
it is added to ORACLE_MODULES.

The checks are the ones the 2026-07-28 audit would have needed:

  metadata      a priced capability must describe itself and declare both schemas —
                an agent picks what to call from exactly this
  determinism   an oracle whose answer changes between identical calls cannot be verified
                by anyone, which is the only thing being sold
  output shape  the output must satisfy the schema the oracle publishes for it. Nothing
                checked this, and "the manifest says something the service does not do"
                was the shape of most of what went wrong today
  refusals      malformed and empty input must come back as a named refusal. A TypeError
                escaping as HTTP 500 tells the caller nothing and gets retried forever —
                fourier.verify did exactly that on {"vector": null}

SAMPLES is explicit rather than schema-derived. Generating inputs from the schema produced
plausible-looking nonsense the oracles rightly rejected, and a test that cannot tell a real
defect from its own bad input is worse than none.
"""

from __future__ import annotations

import copy

import pytest

from oracle_family_app.main import build_family_spec

GRAPH = {"edges": [[0, 1, 1.0], [1, 2, 2.0], [2, 0, 1.5], [0, 3, 2.0], [3, 1, 1.0]]}
POINTS = [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0], [0.5, 0.5]]

SAMPLES: dict[str, dict] = {
    "chronos.eval@v1": {"seed": "conf", "difficulty": 200},
    "lattice.sequence@v1": {"count": 8, "dim": 2},
    "murmuration.aggregate@v1": {"values": [1.0, 2.0, 3.0, 100.0]},
    "lumen.reputation@v1": {"nodes": 4, "edges": GRAPH["edges"]},
    "lumen.score@v1": {"nodes": 4, "edges": GRAPH["edges"], "target_node": 1},
    "colony.optimize@v1": {"points": POINTS},
    # seeded: unseeded blue noise is fresh each call by design, and a seed is how a
    # caller makes it reproducible — that is the property worth pinning.
    "turing.bluenoise@v1": {"count": 8, "seed": 7},
    "percola.threshold@v1": dict(GRAPH),
    "fermat.route@v1": {**GRAPH, "start": 0, "goal": 2},
    "ablation.cascade@v1": dict(GRAPH),
    "landauer.audit@v1": {"ops": [{"id": "a", "gate": "AND", "inputs": []},
                                  {"id": "b", "gate": "NOT", "inputs": ["a"]}]},
    "sortes.draw@v1": {"alpha": "conf"},
    "gauss.field@v1": {"X": [[0.0], [1.0], [2.0]], "y": [0.0, 1.0, 4.0], "query": [[0.5]]},
    "gauss.suggest@v1": {"X": [[0.0], [1.0]], "y": [0.0, 1.0], "bounds": [[0.0, 1.0]]},
    "aestus.seal@v1": {"data": "conf", "T": 800},
    "betti.homology@v1": {"points": POINTS},
    "betti.distance@v1": {"points_a": POINTS, "points_b": POINTS[::-1]},
    "kantor.transport@v1": {"a": [0.5, 0.5], "b": [0.3, 0.7], "cost": [[0.0, 1.0], [1.0, 0.0]]},
    "fourier.spectrum@v1": dict(GRAPH),
}

# Non-deterministic by design: these draw fresh state on every call, which is the product.
NONDETERMINISTIC = {
    # A fresh RSA modulus and key per puzzle is the construction, not a flaw: the sealer
    # must know a factorisation the opener does not.
    "aestus.seal@v1",
    "platon.random@v1", "platon.beacon@v1", "platon.commit@v1",
                    "platon.state@v1", "platon.dream@v1", "platon.oracle@v1",
                    "platon.witnesses@v1", "platon.steer@v1", "platon.project@v1",
                    "platon.reveal@v1", "platon.ask@v1"}

# Malformed inputs every capability must refuse by name rather than crash on.
GARBAGE = [
    pytest.param({}, id="empty"),
    pytest.param({"edges": None, "points": None, "values": None, "ops": None,
                  "X": None, "a": None, "alpha": None, "seed": None, "data": None,
                  "lambda": None, "vector": None, "count": None}, id="all-null"),
    pytest.param({"edges": "not-a-graph", "points": 42, "values": {"x": 1}, "ops": "abc",
                  "X": "abc", "a": True, "count": "many", "seed": [1, 2]}, id="wrong-types"),
]
# A refusal, whatever its wording. Anything else escaping is the bug this looks for:
# oracle_core turns these into {"ok": false, …}; a TypeError or AttributeError becomes 500.
REFUSALS = (ValueError, KeyError)


def _caps():
    return {c.capability_id: c for c in build_family_spec().capabilities}


ALL = sorted(_caps())
WITH_SAMPLE = sorted(SAMPLES)


@pytest.fixture(scope="module")
def caps():
    return _caps()


# ── metadata: true for every capability, no input required ───────

@pytest.mark.parametrize("cid", ALL)
def test_capability_describes_itself(cid, caps):
    c = caps[cid]
    assert c.description and len(c.description) > 20, "an agent chooses what to call from this"
    assert c.price_per_call_usd > 0, "listed for sale, so it must carry a price"
    assert isinstance(c.input_schema, dict) and c.input_schema.get("type") == "object"
    assert isinstance(c.output_schema, dict) and c.output_schema.get("type") == "object"


@pytest.mark.parametrize("cid", ALL)
def test_capability_is_covered_by_a_sample_or_is_platon(cid):
    """Keeps SAMPLES honest: a new oracle cannot slip in without exercising it here.

    Verifiers are exempt because a static sample cannot exercise them — their input is a
    producer's output, which is what test_roundtrip.py drives. Platon is federated, so its
    handlers proxy to a live service rather than compute locally.
    """
    exempt = cid.endswith(".verify@v1") or cid.startswith("platon.") or cid == "aestus.open@v1"
    assert cid in SAMPLES or exempt, (
        f"{cid} has no sample input — add one to SAMPLES so it gets the same checks"
    )


# ── behaviour: for every capability with a sample ────────────────

@pytest.mark.parametrize("cid", WITH_SAMPLE)
def test_same_input_gives_the_same_answer(cid, caps):
    if cid in NONDETERMINISTIC:
        pytest.skip("fresh state on every call is the product")
    a = caps[cid].handler(copy.deepcopy(SAMPLES[cid]))
    b = caps[cid].handler(copy.deepcopy(SAMPLES[cid]))
    assert a == b, "an answer nobody can reproduce is an answer nobody can verify"


@pytest.mark.parametrize("cid", WITH_SAMPLE)
def test_output_satisfies_the_schema_the_oracle_publishes(cid, caps):
    jsonschema = pytest.importorskip("jsonschema")
    c = caps[cid]
    out = c.handler(copy.deepcopy(SAMPLES[cid]))
    jsonschema.validate(out, c.output_schema)


@pytest.mark.parametrize("cid", WITH_SAMPLE)
@pytest.mark.parametrize("bad", GARBAGE)
def test_malformed_input_is_refused_by_name(cid, bad, caps):
    try:
        caps[cid].handler(copy.deepcopy(bad))
    except REFUSALS:
        pass                      # named refusal — becomes {"ok": false, "error": …}
    except Exception as exc:      # noqa: BLE001 — the whole point is to catch the rest
        pytest.fail(
            f"{cid} raised {type(exc).__name__} on malformed input: {exc}. "
            "That escapes as HTTP 500 with no explanation the caller can act on."
        )
