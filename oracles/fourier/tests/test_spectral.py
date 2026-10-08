

# ── verify must compose with spectrum, and refuse rather than crash ──
# `fourier.spectrum@v1` emits fiedler_value/fiedler_vector; verify asked for
# lambda/vector, and neither schema said they were the same thing. Worse, the guard
# tested key presence, so `{"vector": null}` — what you get wiring from a field that does
# not exist — reached float(None) and surfaced as HTTP 500 TypeError.

import pytest

from fourier import capabilities as C

_G = {"edges": [[0, 1, 1.0], [1, 2, 2.0], [2, 0, 1.5], [0, 3, 2.0]]}


def test_spectrum_output_verifies_under_its_own_field_names():
    o = C._spectrum(dict(_G))
    out = C._verify({**_G, "fiedler_value": o["fiedler_value"], "fiedler_vector": o["fiedler_vector"]})
    assert out["valid"] is True


def test_the_documented_names_still_work():
    o = C._spectrum(dict(_G))
    assert C._verify({**_G, "lambda": o["fiedler_value"], "vector": o["fiedler_vector"]})["valid"]


@pytest.mark.parametrize("missing", ["lambda", "vector"])
def test_a_null_field_is_refused_by_name_not_a_crash(missing):
    o = C._spectrum(dict(_G))
    payload = {**_G, "lambda": o["fiedler_value"], "vector": o["fiedler_vector"], missing: None}
    with pytest.raises(ValueError, match=missing):
        C._verify(payload)
