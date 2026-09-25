"""Smoke tests — family manifest aggregates every oracle_core package."""

from oracle_family_app.main import ORACLE_MODULES, build_family_spec


def test_oracle_modules_include_new_oracles():
    assert "percola" in ORACLE_MODULES
    assert "fermat" in ORACLE_MODULES
    assert "ablation" in ORACLE_MODULES
    assert "landauer" in ORACLE_MODULES


def test_family_spec_exports_all_capabilities():
    spec = build_family_spec()
    ids = {c.capability_id for c in spec.capabilities}
    # 42 = all 11 capabilities Platon serves + 31 across sixteen oracle_core oracles. Two corrections got
    # it here: platon.verify@v1 was in PLATON_CAPS while Platon answers "Unknown
    # capability" for it, and the Dockerfile copied only ten of the sixteen oracles, so six
    # were skipped at every boot with "No module named" and were never sold.
    assert len(ids) == 42
    assert "platon.verify@v1" not in ids, (
        "platon.verify@v1 is not implemented by Platon; listing it sells a 500"
    )
    for prefix in (
        "platon.",
        "chronos.",
        "lattice.",
        "murmuration.",
        "lumen.",
        "colony.",
        "turing.",
        "percola.",
        "fermat.",
        "ablation.",
        "landauer.",
        # The six the Dockerfile used to omit — a missing COPY line must fail the test,
        # not silently shrink the catalogue.
        "sortes.",
        "gauss.",
        "aestus.",
        "betti.",
        "kantor.",
        "fourier.",
    ):
        assert any(x.startswith(prefix) for x in ids), prefix
