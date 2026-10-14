"""Federating a capability means federating its schemas too.

The family lists Platon's eleven capabilities and proxies invokes to it. It declared only
id, description and price, so every federated row inherited oracle_core's "no fields"
default — `input_schema: {"type": "object", "properties": {}}` — while Platon itself
documents `num_bytes`, `client_seed`, `prompt`, `round`, `question` and the rest.

That default is indistinguishable from a real "takes no input" (which `platon.state@v1`
genuinely is), and it travelled: onto the family manifest, into every hub that federated
us, and out to the public catalogue, where eleven capabilities could be found, priced and
routed to — but not filled in. The conformance suite's metadata check did not catch it
because a default schema is still a schema: it asserted presence, not usefulness.

The fix carries Platon's own declarations through instead of restating them here, because
anything restated by hand is the drift that put `platon.verify@v1` on sale.
"""

from __future__ import annotations

import pytest

import oracle_family_app.main as family

RANDOM_IN = {
    "type": "object",
    "properties": {
        "num_bytes": {"type": "integer", "minimum": 1, "maximum": 64, "default": 32},
        "client_seed": {"type": "string"},
    },
}
RANDOM_OUT = {
    "type": "object",
    "required": ["random_hex", "proof", "signature"],
    "properties": {"random_hex": {"type": "string"}},
}
STATE_IN = {"type": "object", "properties": {}}


def _fake_platon(tools, *, boom: bool = False):
    """Stand in for Platon's /ai-market/v2/manifest over the httpx client."""

    class _Response:
        def json(self):
            return {"tools": tools}

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def get(self, url):
            if boom:
                raise RuntimeError("connection refused")
            return _Response()

    return _Client


@pytest.fixture
def platon_serving(monkeypatch):
    """Point the family at a fake Platon and hand back its capability list."""

    def _serve(tools, *, boom: bool = False):
        import httpx

        monkeypatch.setattr(httpx, "Client", _fake_platon(tools, boom=boom))
        return family.platon_federated_capabilities()

    return _serve


def _by_id(caps):
    return {c.capability_id: c for c in caps}


class TestSchemasAreCarriedThrough:
    def test_platon_declarations_arrive_verbatim(self, platon_serving):
        caps = _by_id(platon_serving([
            {"capability_id": "platon.random@v1",
             "input_schema": RANDOM_IN, "output_schema": RANDOM_OUT},
        ]))
        assert caps["platon.random@v1"].input_schema == RANDOM_IN
        assert caps["platon.random@v1"].output_schema == RANDOM_OUT

    def test_a_genuinely_inputless_capability_keeps_an_explicit_empty_schema(
        self, platon_serving,
    ):
        """`platon.state@v1` really takes nothing — the point is that it SAYS so."""
        caps = _by_id(platon_serving([
            {"capability_id": "platon.state@v1", "input_schema": STATE_IN},
        ]))
        schema = caps["platon.state@v1"].input_schema
        assert schema == STATE_IN
        assert "properties" in schema, "explicitly empty, not merely unknown"

    def test_the_defect_itself_is_pinned(self, platon_serving):
        """No federated row may advertise no fields for a capability that has them."""
        served = [
            {"capability_id": "platon.random@v1", "input_schema": RANDOM_IN},
            {"capability_id": "platon.steer@v1",
             "input_schema": {"type": "object", "properties": {"prompt": {"type": "string"}}}},
            {"capability_id": "platon.ask@v1",
             "input_schema": {"type": "object",
                              "properties": {"question": {"type": "string"},
                                             "lang": {"type": "string"}}}},
        ]
        caps = _by_id(platon_serving(served))
        for row in served:
            declared = set(row["input_schema"]["properties"])
            federated = set(caps[row["capability_id"]].input_schema.get("properties") or {})
            assert federated == declared, row["capability_id"]

    def test_every_declared_capability_is_still_federated(self, platon_serving):
        """Pass-through must not become a filter: an unmatched row keeps its defaults."""
        caps = platon_serving([{"capability_id": "platon.random@v1", "input_schema": RANDOM_IN}])
        assert len(caps) == len(family.PLATON_CAPS)
        assert {c.capability_id for c in caps} == {cid for cid, _, _ in family.PLATON_CAPS}


class TestFailOpen:
    def test_unreachable_platon_still_federates(self, platon_serving):
        """A neighbour that is down for five seconds is not a missing capability."""
        caps = platon_serving([], boom=True)
        assert len(caps) == len(family.PLATON_CAPS)
        # oracle_core's defaults, i.e. "unknown" — never a crash and never a guess.
        assert caps[0].input_schema == {"type": "object", "properties": {}}

    @pytest.mark.parametrize("value", [{}, None, "not-a-schema", []])
    def test_emptiness_never_overwrites_the_default(self, platon_serving, value):
        caps = _by_id(platon_serving([
            {"capability_id": "platon.random@v1", "input_schema": value},
        ]))
        assert caps["platon.random@v1"].input_schema == {"type": "object", "properties": {}}


class TestDriftWarningStillWorks:
    def test_a_capability_platon_does_not_serve_is_reported(self, platon_serving, capsys):
        platon_serving([{"capability_id": "platon.random@v1", "input_schema": RANDOM_IN}])
        out = capsys.readouterr().out
        assert "does not serve" in out
        assert "platon.state@v1" in out

    def test_silence_when_platon_is_unreachable(self, platon_serving, capsys):
        """Fail-open means no false accusation of drift when we simply could not look."""
        platon_serving([], boom=True)
        out = capsys.readouterr().out
        assert "does not serve" not in out
        assert "could not read Platon's manifest" in out
