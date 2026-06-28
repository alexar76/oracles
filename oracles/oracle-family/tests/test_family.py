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
    assert len(ids) == 23
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
    ):
        assert any(x.startswith(prefix) for x in ids), prefix
