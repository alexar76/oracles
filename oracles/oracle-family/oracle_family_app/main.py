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
from typing import Any

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
# Hand-maintained, so it can drift from what Platon actually implements — and it had:
# `platon.verify@v1` was advertised here, in the family manifest, and onward to any hub
# that federated us, while Platon answered `Unknown capability: platon.verify@v1`. The
# family turned that refusal into a bare 500. `_warn_on_unknown_platon_caps()` below now
# compares this list against Platon's live manifest at startup and logs any id Platon
# does not serve, so the next drift is visible instead of being sold.
PLATON_CAPS = [
    ("platon.random@v1", "Signed chaos-VRF randomness", 0.004),
    ("platon.beacon@v1", "Hash-chained randomness beacon round", 0.004),
    ("platon.commit@v1", "Commit-reveal (bias-resistant) randomness", 0.004),
    ("platon.oracle@v1", "LLM mathematical witness at bifurcations", 0.02),
    ("platon.ask@v1", "Grounded, read-only informational guide", 0.003),
    # The other six Platon serves. Federating only five meant a hub had to keep a second,
    # separately-trusted peer row pointed straight at the Platon host to reach these — and
    # the row that did so on modelmarket.dev was crawled once in June, has answered 404 on
    # its manifest ever since, and could not be retired without losing them. Descriptions
    # and prices taken from Platon's own manifest; all six verified against the live
    # service with schema-correct inputs.
    ("platon.state@v1", "Snapshot of the 32D universe — telemetry, oscillators, projection", 0.001),
    ("platon.steer@v1", "Semantic steering — natural language maps to bifurcation parameters", 0.005),
    ("platon.project@v1", "Rotate the Stiefel projection — how the 32D shadow appears in 2D", 0.002),
    ("platon.dream@v1", "Surrogate vs truth trajectory — see where prediction dies at chaos", 0.008),
    ("platon.reveal@v1", "Commit-reveal randomness, phase 2 — supply the round", 0.004),
    ("platon.witnesses@v1", "Public feed of oracle testimonies — chimera births, chaos thresholds", 0.001),
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
            if resp.status_code >= 400:
                # Platon is its own app, not an oracle_core one, so it answers a bare
                # "500 Internal Server Error" when a required input is absent — e.g.
                # platon.steer without `prompt`. raise_for_status() would surface that as an
                # httpx error with no explanation for the caller, so carry whatever Platon
                # did say and let oracle_core turn it into {"ok": false, "error": …}.
                detail = (resp.text or "").strip()[:200] or resp.reason_phrase
                raise RuntimeError(
                    f"{cap_id} refused upstream (HTTP {resp.status_code}): {detail}"
                )
            data = resp.json()
        if isinstance(data, dict) and data.get("ok") is False:
            raise RuntimeError(data.get("error", "platon invoke failed"))
        return data.get("output", data) if isinstance(data, dict) else data

    return handler


def _platon_served_tools() -> dict[str, dict[str, Any]]:
    """Platon's own manifest rows, keyed by capability id. Empty when unreachable.

    Read ONCE at startup and used for two things: the drift check below, and the
    input/output schemas we federate. Platon is the authority on both — it is a live
    service with its own declarations, not an oracle_core spec we own — so anything we
    restate here by hand can only drift from it.

    Fail-open on purpose: a momentarily down neighbour is not the same as a capability
    that does not exist, so the family still boots and still federates Platon.
    """
    import httpx

    try:
        with httpx.Client(timeout=5.0) as client:
            tools = client.get(f"{PLATON_URL}/ai-market/v2/manifest").json().get("tools") or []
    except Exception as exc:  # noqa: BLE001 — advisory read, never blocks startup
        print(
            f"[oracle-family] could not read Platon's manifest ({exc}); federating as "
            "declared, with schemas unknown"
        )
        return {}
    return {
        str(t.get("capability_id")): t
        for t in tools
        if isinstance(t, dict) and t.get("capability_id")
    }


def _warn_on_unknown_platon_caps(served: dict[str, dict[str, Any]]) -> None:
    """Log any PLATON_CAPS id Platon does not actually serve.

    Advisory only. The check exists so the *drift* is visible — `platon.verify@v1` sat in
    this list, in the manifest, and in every hub that federated us, and nothing said a
    word until someone invoked it.
    """
    if not served:
        return
    missing = [cid for cid, _, _ in PLATON_CAPS if cid not in served]
    if missing:
        print(
            "[oracle-family] WARNING: advertising capabilities Platon does not serve: "
            f"{', '.join(missing)} — invokes will be refused. Remove them from PLATON_CAPS."
        )


def platon_federated_capabilities() -> list[Capability]:
    """Federate Platon's capabilities, carrying its own schemas through.

    Declaring only id/description/price left every federated Platon row advertising
    `input_schema: {"type": "object", "properties": {}}` — oracle_core's "no fields"
    default — while Platon itself documents `num_bytes`, `client_seed`, `prompt`,
    `round`, `question` and the rest. That reached the public hub manifest: eleven
    capabilities that a buyer, an agent, or a graph builder could see, price, and route
    to, but could not fill in. Nothing had to be restated to fix it; the schemas just
    had to be passed along.
    """
    served = _platon_served_tools()
    _warn_on_unknown_platon_caps(served)

    caps: list[Capability] = []
    carried = 0
    for cid, desc, price in PLATON_CAPS:
        tool = served.get(cid) or {}
        schemas: dict[str, Any] = {}
        for field_name in ("input_schema", "output_schema"):
            value = tool.get(field_name)
            # An absent or `{}` schema is no information; oracle_core's own default says
            # the same thing more precisely, so don't overwrite it with emptiness.
            if isinstance(value, dict) and value:
                schemas[field_name] = value
        if schemas:
            carried += 1
        caps.append(Capability(
            capability_id=cid, description=desc, handler=_platon_proxy(cid),
            product_id="prod-platon", price_per_call_usd=price, **schemas,
        ))

    if served:
        print(
            f"[oracle-family] Platon schemas carried through for {carried}/{len(PLATON_CAPS)} "
            "federated capabilities"
        )
    return caps


def load_specs() -> list[tuple[str, OracleSpec]]:
    """Import each oracle's SPEC; skip (loudly) any that fails to import."""
    specs: list[tuple[str, OracleSpec]] = []
    for name in ORACLE_MODULES:
        try:
            mod = importlib.import_module(f"{name}.capabilities")
            spec = getattr(mod, "SPEC")
            specs.append((name, spec))
        except ModuleNotFoundError as exc:
            # A genuinely absent oracle is a legitimate partial deployment — the family is
            # meant to serve whichever siblings are installed, so degrade and say so.
            print(f"[oracle-family] skipping {name}: not installed ({exc})")
        except Exception as exc:
            # Anything else means the module IS on the path and failed to load: a version
            # mismatch against oracle-core, a syntax error, a bad schema. Degrading here is
            # what let the family boot HTTP 200 while silently serving 5 fewer capabilities
            # than its own manifest promised — indistinguishable, to a buyer or to the hub
            # indexing it, from those capabilities never having existed. A broken install is
            # worth failing on; a missing one is not.
            raise RuntimeError(
                f"oracle {name!r} is installed but its capabilities failed to load: "
                f"{type(exc).__name__}: {exc}. This is a broken install, not a partial one — "
                f"if aimarket-oracle-core is older than 0.3, that is the cause."
            ) from exc
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
