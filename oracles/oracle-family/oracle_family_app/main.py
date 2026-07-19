"""AIMarket Oracle Family — one endpoint, every oracle_core oracle.

Aggregates the priced capabilities of every oracle_core oracle (chronos,
lattice, murmuration, lumen, colony, turing, percola, fermat, ablation,
landauer) into a single ``OracleSpec`` so one
container exposes ONE AIMarket v2 manifest with all their capability groups —
"один hub-manifest с N capability-группами". Each capability keeps its own
``product_id``, so receipts stay correctly attributed per oracle; the family
signs them with one key.

Platon ships separately as its own full app (frontend + UMBRAL cave).

Run:  python -m oracle_family_app.main   (PORT 9400)
"""

from __future__ import annotations

import importlib
import os

from oracle_core import Capability, OracleSpec, create_app

# oracle_core oracles that expose ``<pkg>.capabilities.SPEC`` (pure functions).
ORACLE_MODULES = [
    "chronos",
    "lattice",
    "murmuration",
    "lumen",
    "colony",
    "turing",
    "percola",
    "fermat",
    "ablation",
    "landauer",
    "sortes",
    "gauss",
    "aestus",
    "betti",
    "kantor",
    "fourier",
]

# Platon — oracle #1, the flagship — is a LIVE dynamical service (its own chaos
# engine + the UMBRAL cave UI), not a pure oracle_core spec. So the family
# FEDERATES it: its capabilities appear in this manifest and invokes are proxied
# to the live Platon service, which stays authoritative. (The cave UI is a
# separate app.)
PLATON_URL = (os.environ.get("ORACLE_FAMILY_PLATON_URL") or "http://127.0.0.1:9200").rstrip("/")
PLATON_CAPS = [
    ("platon.verify@v1", "Verify a signed chaos-VRF draw", 0.001),
    ("platon.random@v1", "Signed chaos-VRF randomness", 0.004),
    ("platon.beacon@v1", "Hash-chained randomness beacon round", 0.004),
    ("platon.commit@v1", "Commit-reveal (bias-resistant) randomness", 0.004),
    ("platon.oracle@v1", "LLM mathematical witness at bifurcations", 0.02),
    ("platon.ask@v1", "Grounded, read-only informational guide", 0.003),
]


def _platon_proxy(cap_id: str):
    """Invoke handler that forwards to the live Platon oracle service."""
    def handler(input_data: dict):
        import httpx

        with httpx.Client(timeout=20.0) as client:
            resp = client.post(
                f"{PLATON_URL}/ai-market/v2/invoke",
                json={"capability_id": cap_id, "input": input_data},
            )
            resp.raise_for_status()
            data = resp.json()
        if isinstance(data, dict) and data.get("ok") is False:
            raise RuntimeError(data.get("error", "platon invoke failed"))
        return data.get("output", data) if isinstance(data, dict) else data

    return handler


def platon_federated_capabilities() -> list[Capability]:
    return [
        Capability(
            capability_id=cid, description=desc, handler=_platon_proxy(cid),
            product_id="prod-platon", price_per_call_usd=price,
        )
        for cid, desc, price in PLATON_CAPS
    ]


def load_specs() -> list[tuple[str, OracleSpec]]:
    """Import each oracle's SPEC; skip (loudly) any that fails to import."""
    specs: list[tuple[str, OracleSpec]] = []
    for name in ORACLE_MODULES:
        try:
            mod = importlib.import_module(f"{name}.capabilities")
            spec = getattr(mod, "SPEC")
            specs.append((name, spec))
        except Exception as exc:  # missing package/dep — degrade, don't crash
            print(f"[oracle-family] skipping {name}: {exc}")
    return specs


def build_family_spec() -> OracleSpec:
    specs = load_specs()
    caps = []
    seen: set[str] = set()
    # Platon is oracle #1 (the flagship) — list it first, then the oracle_core oracles.
    for cap in platon_federated_capabilities():
        if cap.capability_id not in seen:
            seen.add(cap.capability_id)
            caps.append(cap)
    for _, spec in specs:
        for cap in spec.capabilities:
            if cap.capability_id in seen:
                continue
            seen.add(cap.capability_id)
            caps.append(cap)
    print(f"[oracle-family] {len(specs) + 1} oracles (Platon #1 federated + {len(specs)} oracle_core), "
          f"{len(caps)} capabilities: {', '.join(c.capability_id for c in caps)}")
    return OracleSpec(
        name="AIMarket Oracle Family",
        product_id="prod-oracle-family",
        description=(
            "Unified endpoint for the AIMarket oracle family — verifiable randomness, "
            "delay (VDF), robust consensus, reputation, optimization, structured "
            "sampling, percolation resilience, least-time routing, cascade risk, "
            "and thermodynamic audit. One manifest, every oracle's capabilities; "
            "each result is Ed25519-signed with a per-call receipt."
        ),
        public_url=os.environ.get("ORACLE_FAMILY_PUBLIC_URL", "https://oracles.modelmarket.dev/family"),
        categories=[
            "oracle", "randomness-beacon", "verifiable-delay", "consensus",
            "reputation", "optimization", "sampling", "percolation", "routing",
            "cascade-risk", "thermodynamics", "agent-tooling",
        ],
        capabilities=caps,
        signing_key_path=os.environ.get("ORACLE_FAMILY_SIGNING_KEY", "data/oracle_family_signing_key"),
        related=["https://github.com/alexar76/oracles"],
    )


SPEC = build_family_spec()
app = create_app(SPEC, cors_origins=os.environ.get("ORACLE_FAMILY_CORS_ORIGINS", "*"))


def main() -> None:
    import uvicorn

    uvicorn.run(
        "oracle_family_app.main:app",
        host=os.environ.get("ORACLE_FAMILY_HOST", "0.0.0.0"),
        port=int(os.environ.get("ORACLE_FAMILY_PORT", "9400")),
        reload=False,
    )


if __name__ == "__main__":
    main()
