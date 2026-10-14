"""-1 has order 2 in Z_N*: y and N - y both verify for the same (g, T) (2026-10-12).

A raw y is therefore not unique — a prover could pick either. The output is the class
|y| = min(y, N - y); both proofs must map to the same canonical value and digest.
"""

from chronos import vdf

N = vdf.RSA_2048


def _negated_proof(g, y, T):
    y2 = N - y
    l2 = vdf.hash_to_prime(g, y2, T)
    return y2, N - pow(g, (1 << T) // l2, N), l2


def test_both_signs_verify_and_prove_one_output():
    g = vdf.hash_to_group("beacon-round-42")
    T = 1500
    honest = vdf.run("beacon-round-42", T)
    y = int(honest["y"])
    p = honest["proof"]
    assert vdf.verify(g, y, T, int(p["pi"]), int(p["l"]))
    y2, pi2, l2 = _negated_proof(g, y, T)
    assert vdf.verify(g, y2, T, pi2, l2), "the ambiguity this test documents"
    assert vdf.canonical(y) == vdf.canonical(y2) == int(honest["y_canonical"])
    assert vdf.output_digest(g, T, y) == vdf.output_digest(g, T, y2) == honest["output"]
    assert vdf.canonical(y) <= (N - 1) // 2


def test_the_verify_capability_reports_the_canonical_output_for_either_sign():
    from chronos.capabilities import _verify
    honest = vdf.run("cap-check", 800)
    g, T = int(honest["g"]), 800
    y2, pi2, l2 = _negated_proof(g, int(honest["y"]), T)
    a = _verify({"g": honest["g"], "y": honest["y"], "difficulty": T, "proof": honest["proof"]})
    b = _verify({"g": honest["g"], "y": str(y2), "difficulty": T, "proof": {"pi": str(pi2), "l": str(l2)}})
    assert a["valid"] and b["valid"]
    assert a["y_canonical"] == b["y_canonical"] == honest["y_canonical"]
    assert a["output"] == b["output"] == honest["output"]
