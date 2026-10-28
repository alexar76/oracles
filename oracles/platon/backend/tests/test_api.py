import os
import sys

import pytest
from httpx import ASGITransport, AsyncClient

from oracle_platon.main import app
from oracle_platon.randomness import verify_randomness
from oracle_platon.signing import Signer
from oracle_platon.simulation import SimulationEngine


pytestmark = pytest.mark.usefixtures("local_http_opt_in")


@pytest.fixture
def isolated_engine(monkeypatch):
    eng = SimulationEngine()
    eng.state.reset_random(seed=1)
    monkeypatch.setattr("oracle_platon.main.engine", eng)
    monkeypatch.setattr("oracle_platon.aimarket.engine", eng)
    return eng


@pytest.mark.asyncio
async def test_health(isolated_engine):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://localhost") as client:
        resp = await client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"


@pytest.mark.asyncio
async def test_state_telemetry(isolated_engine):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://localhost") as client:
        resp = await client.get("/api/state")
    data = resp.json()
    assert "kappa" in data
    assert "order_parameter" in data
    assert "oscillators" in data
    assert len(data["oscillators"]["amplitudes"]) == 32


@pytest.mark.asyncio
async def test_steer(isolated_engine):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://localhost") as client:
        resp = await client.post("/api/steer", json={"prompt": "chimera at 0.73"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["applied"] is True
    assert 0.15 <= data["kappa"] <= 1.35


@pytest.mark.asyncio
async def test_dream(isolated_engine):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://localhost") as client:
        resp = await client.get("/api/dream?steps=20")
    data = resp.json()
    assert len(data["surrogate"]) == 20
    assert len(data["truth"]) == 20


@pytest.mark.asyncio
async def test_well_known():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://localhost") as client:
        resp = await client.get("/.well-known/ai-market.json")
    data = resp.json()
    assert data["protocol_version"] == "v2"
    assert data["name"] == "Platon Shadow Oracle"
    assert data["manifest_url"].endswith("/ai-market/v2/manifest")
    assert data["signer_public_key"]
    assert "platon" in data["ecosystem"]["project"]


@pytest.mark.asyncio
async def test_manifest():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://localhost") as client:
        resp = await client.get("/ai-market/v2/manifest")
    data = resp.json()
    assert data["capabilities_count"] >= 6
    assert data["signature"]["algorithm"] == "ed25519"
    assert data["signature"]["value"]
    ids = {t["capability_id"] for t in data["tools"]}
    assert "platon.steer@v1" in ids


@pytest.mark.asyncio
async def test_invoke_state(isolated_engine):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://localhost") as client:
        resp = await client.post(
            "/ai-market/v2/invoke",
            json={"capability_id": "platon.state@v1", "input": {}},
        )
    data = resp.json()
    assert data["ok"] is True
    assert "order_parameter" in data["output"]


@pytest.mark.asyncio
async def test_invoke_steer(isolated_engine):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://localhost") as client:
        resp = await client.post(
            "/ai-market/v2/invoke",
            json={
                "capability_id": "platon.steer@v1",
                "input": {"prompt": "figure-eight bleeding"},
            },
        )
    data = resp.json()
    assert data["ok"] is True
    assert data["output"]["applied"] is True


@pytest.mark.asyncio
async def test_invoke_random_is_verifiable(isolated_engine):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://localhost") as client:
        resp = await client.post(
            "/ai-market/v2/invoke",
            json={
                "capability_id": "platon.random@v1",
                "input": {"num_bytes": 16, "client_seed": "mesh-node-7"},
            },
        )
    data = resp.json()
    assert data["ok"] is True
    out = data["output"]
    assert len(bytes.fromhex(out["random_hex"])) == 16
    assert out["proof"]["scheme"] == "platon-chaos-vrf/v1"
    # signature verifies against the embedded public key
    assert verify_randomness(out, out["signature"]["public_key"]) is True


@pytest.mark.asyncio
async def test_invoke_verify_random_capability(isolated_engine):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://localhost") as client:
        draw = await client.post(
            "/ai-market/v2/invoke",
            json={"capability_id": "platon.random@v1", "input": {"num_bytes": 8}},
        )
        out = draw.json()["output"]
        verify = await client.post(
            "/ai-market/v2/invoke",
            json={
                "capability_id": "platon.verify@v1",
                "input": {
                    "random_hex": out["random_hex"],
                    "proof": out["proof"],
                    "signature": out["signature"],
                },
            },
        )
    data = verify.json()
    assert data["ok"] is True
    assert data["output"]["valid"] is True


@pytest.mark.asyncio
async def test_invoke_envelope_has_signed_receipt(isolated_engine):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://localhost") as client:
        resp = await client.post(
            "/ai-market/v2/invoke",
            json={"capability_id": "platon.state@v1", "input": {}},
        )
    data = resp.json()
    receipt = data["receipt"]
    assert receipt["capability_id"] == "platon.state@v1"
    assert receipt["signature"]["algorithm"] == "ed25519"
    assert Signer("data/platon_signing_key").verify_receipt(receipt) is True
    # provenance hash is a real sha256 (64 hex chars), not a truncated string
    assert len(data["provenance"]["input_hash"]) == 64
    int(data["provenance"]["input_hash"], 16)


@pytest.mark.asyncio
async def test_invoke_beacon_chains(isolated_engine):
    from oracle_platon.aimarket import beacon
    from oracle_platon.randomness import verify_beacon_chain

    beacon.rounds.clear()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://localhost") as client:
        for i in range(3):
            await client.post(
                "/ai-market/v2/invoke",
                json={"capability_id": "platon.beacon@v1", "input": {"client_seed": str(i)}},
            )
        resp = await client.get("/api/beacon?limit=10")
    data = resp.json()
    assert data["chain_length"] == 3
    assert data["chain_valid"] is True
    assert verify_beacon_chain(data["rounds"]) is True


@pytest.mark.asyncio
async def test_manifest_self_verifies_and_has_random(isolated_engine):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://localhost") as client:
        resp = await client.get("/ai-market/v2/manifest")
    data = resp.json()
    ids = {t["capability_id"] for t in data["tools"]}
    assert "platon.random@v1" in ids
    assert Signer("data/platon_signing_key").verify_manifest_signature(data) is True


@pytest.mark.asyncio
async def test_metrics_are_measured_after_invokes(isolated_engine):
    from oracle_platon.metrics import metrics

    metrics.reset()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://localhost") as client:
        for _ in range(3):
            await client.post(
                "/ai-market/v2/invoke",
                json={"capability_id": "platon.state@v1", "input": {}},
            )
        resp = await client.get("/ai-market/v2/manifest")
    tool = next(
        t for t in resp.json()["tools"] if t["capability_id"] == "platon.state@v1"
    )
    assert tool["metrics_source"] == "measured"
    assert tool["calls_observed"] >= 3


@pytest.mark.asyncio
async def test_pca_energy_in_range(isolated_engine):
    val = isolated_engine.telemetry()["pca_energy_3"]
    assert 0.0 <= val <= 1.0


@pytest.mark.asyncio
async def test_ask_returns_grounded_answer(isolated_engine):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://localhost") as client:
        resp = await client.post(
            "/api/ask", json={"question": "What is kappa right now?", "lang": "en"}
        )
    data = resp.json()
    assert resp.status_code == 200
    assert data["lang"] == "en"
    assert len(data["answer"]) > 0
    # without an LLM configured we get the deterministic fallback, grounded in live state
    assert data["source"] == "fallback"
    assert "kappa" in data["answer"]


@pytest.mark.asyncio
async def test_ask_is_localized(isolated_engine):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://localhost") as client:
        resp = await client.post("/api/ask", json={"question": "что это?", "lang": "ru"})
    assert resp.json()["lang"] == "ru"


@pytest.mark.asyncio
async def test_ask_capability_invoke(isolated_engine):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://localhost") as client:
        resp = await client.post(
            "/ai-market/v2/invoke",
            json={"capability_id": "platon.ask@v1", "input": {"question": "hi", "lang": "es"}},
        )
    data = resp.json()
    assert data["ok"] is True
    assert "answer" in data["output"]
    assert data["output"]["lang"] == "es"


@pytest.mark.asyncio
async def test_ask_rate_limited(isolated_engine):
    from oracle_platon.main import _ask_limiter

    _ask_limiter._buckets.clear()
    transport = ASGITransport(app=app)
    statuses = []
    async with AsyncClient(transport=transport, base_url="http://localhost") as client:
        for _ in range(_ask_limiter.limit + 2):
            r = await client.post("/api/ask", json={"question": "q", "lang": "en"})
            statuses.append(r.status_code)
    assert 429 in statuses
    _ask_limiter._buckets.clear()


@pytest.mark.asyncio
async def test_invoke_rate_limited(isolated_engine):
    from oracle_platon.main import _invoke_limiter

    _invoke_limiter._buckets.clear()
    transport = ASGITransport(app=app)
    statuses = []
    async with AsyncClient(transport=transport, base_url="http://localhost") as client:
        for _ in range(_invoke_limiter.limit + 2):
            r = await client.post(
                "/ai-market/v2/invoke",
                json={"capability_id": "platon.state@v1", "input": {}},
            )
            statuses.append(r.status_code)
    assert 429 in statuses
    _invoke_limiter._buckets.clear()


@pytest.mark.asyncio
async def test_dream_rate_limited(isolated_engine):
    from oracle_platon.main import _dream_limiter

    _dream_limiter._buckets.clear()
    transport = ASGITransport(app=app)
    statuses = []
    async with AsyncClient(transport=transport, base_url="http://localhost") as client:
        for _ in range(_dream_limiter.limit + 2):
            r = await client.get("/api/dream?steps=12")
            statuses.append(r.status_code)
    assert 429 in statuses
    _dream_limiter._buckets.clear()


@pytest.mark.asyncio
async def test_commit_reveal_via_invoke(isolated_engine):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://localhost") as client:
        c = await client.post(
            "/ai-market/v2/invoke", json={"capability_id": "platon.commit@v1", "input": {}}
        )
        rnd = c.json()["output"]["round"]
        r = await client.post(
            "/ai-market/v2/invoke",
            json={"capability_id": "platon.reveal@v1", "input": {"round": rnd, "client_seed": "z"}},
        )
    out = r.json()["output"]
    from oracle_platon.commit_reveal import verify_reveal

    assert verify_reveal(out, out["signature"]["public_key"]) is True


@pytest.mark.asyncio
async def test_invoke_unknown_capability():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://localhost") as client:
        resp = await client.post(
            "/ai-market/v2/invoke",
            json={"capability_id": "platon.nope@v1", "input": {}},
        )
    data = resp.json()
    assert data["ok"] is False


@pytest.mark.asyncio
async def test_invoke_logs_agent_activity(isolated_engine):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://localhost") as client:
        await client.post(
            "/ai-market/v2/invoke",
            json={
                "capability_id": "platon.steer@v1",
                "input": {"prompt": "agent probe"},
            },
        )
        resp = await client.get("/api/activity?limit=10")
    activity = resp.json()["activity"]
    invokes = [a for a in activity if a["kind"] == "agent_invoke"]
    assert len(invokes) >= 1
    assert invokes[0]["payload"]["capability_id"] == "platon.steer@v1"
    assert invokes[0]["payload"]["source"] == "aimarket-agent"


# Without PLATON_STEER_TOKEN the steer/project writes are this machine's own, not anybody's
# who can reach the port (the server binds 0.0.0.0).


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "base_url, headers",
    [
        ("http://platon.example", {}),  # a rebinding name, or any Host but a loopback one
        ("http://localhost", {"X-Forwarded-For": "93.184.216.34"}),  # relayed by a local proxy
        ("http://localhost", {"X-Real-IP": "93.184.216.34"}),
        ("http://localhost", {"Origin": "https://evil.example"}),  # a page in the user's browser
        ("http://localhost", {"Origin": "null"}),
    ],
)
async def test_tokenless_steer_refused_unless_local(isolated_engine, monkeypatch, base_url, headers):
    monkeypatch.delenv("PLATON_STEER_TOKEN", raising=False)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url=base_url, headers=headers) as client:
        resp = await client.post("/api/steer", json={"prompt": "chimera at 0.73"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_tokenless_steer_refused_from_another_host(isolated_engine, monkeypatch):
    monkeypatch.delenv("PLATON_STEER_TOKEN", raising=False)
    transport = ASGITransport(app=app, client=("93.184.216.34", 40000))
    async with AsyncClient(transport=transport, base_url="http://localhost") as client:
        resp = await client.post("/api/steer", json={"prompt": "chimera at 0.73"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_tokenless_steer_from_a_local_page(isolated_engine, monkeypatch):
    monkeypatch.delenv("PLATON_STEER_TOKEN", raising=False)
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport, base_url="http://127.0.0.1:9450", headers={"Origin": "http://localhost:5173"}
    ) as client:
        resp = await client.post("/api/steer", json={"prompt": "chimera at 0.73"})
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_token_opens_steer_to_any_caller(isolated_engine, monkeypatch):
    monkeypatch.setenv("PLATON_STEER_TOKEN", "s3cret")
    transport = ASGITransport(app=app, client=("93.184.216.34", 40000))
    async with AsyncClient(transport=transport, base_url="http://platon.example") as client:
        bad = await client.post("/api/steer", json={"prompt": "x"}, headers={"X-Platon-Token": "nope"})
        good = await client.post("/api/steer", json={"prompt": "x"}, headers={"X-Platon-Token": "s3cret"})
    assert bad.status_code == 401
    assert good.status_code == 200


@pytest.mark.asyncio
async def test_a_public_demo_opens_tokenless_writes_on_purpose(isolated_engine, monkeypatch):
    monkeypatch.delenv("PLATON_STEER_TOKEN", raising=False)
    monkeypatch.setenv("PLATON_PUBLIC_WRITES", "1")
    transport = ASGITransport(app=app, client=("172.18.0.5", 40000))  # the frontend's nginx
    async with AsyncClient(transport=transport, base_url="http://platon.example",
                           headers={"X-Forwarded-For": "93.184.216.34"}) as client:
        resp = await client.post("/api/steer", json={"prompt": "chimera at 0.73"})
    assert resp.status_code == 200


_TABLE_HEADER = ("  sl  local_address rem_address   st tx_queue rx_queue tr tm->when retrnsmt"
                 "   uid  timeout inode\n")


def _socket_table(tmp_path, caller: str, server: str, uid):
    """A /proc/net/tcp holding the server's end of the connection (ours) and the caller's end
    owned by `uid`, or no caller's end when uid is None. Endpoints in the kernel's format."""
    row = "   {n}: {a} {b} 01 00000000:00000000 00:00000000 00000000  {u}        0 {n}00 1 0 20 4 30 10 -1\n"
    lines = [_TABLE_HEADER, row.format(n=1, a=server, b=caller, u=os.geteuid())]
    if uid is not None:
        lines.append(row.format(n=2, a=caller, b=server, u=uid))
    path = tmp_path / "tcp"
    path.write_text("".join(lines))
    return (str(path),)


@pytest.mark.asyncio
@pytest.mark.skipif(not hasattr(os, "geteuid") or sys.byteorder != "little", reason="POSIX table")
@pytest.mark.parametrize("owner,opt_in,want", [
    ("self", False, 401), ("self", True, 200), ("other", True, 401), ("absent", True, 401),
])
async def test_tokenless_steer_requires_explicit_tcp_trust_and_matching_owner(
    isolated_engine, monkeypatch, tmp_path, owner, opt_in, want
):
    # A same-user worker may relay remote requests with no listener of its own.
    # Socket ownership alone must never grant keyless access by default.
    import oracle_platon.main as main_mod

    monkeypatch.delenv("PLATON_STEER_TOKEN", raising=False)
    monkeypatch.delenv("PLATON_PUBLIC_WRITES", raising=False)
    monkeypatch.setenv("PLATON_LOCAL_RELAY", "1" if opt_in else "0")
    uid = {"self": os.geteuid(), "other": os.geteuid() + 1, "absent": None}[owner]
    monkeypatch.setattr(main_mod, "_PROC_NET_TCP",
                        _socket_table(tmp_path, "0100007F:9C40", "0100007F:24EA", uid))
    transport = ASGITransport(app=app, client=("127.0.0.1", 40000))
    async with AsyncClient(transport=transport, base_url="http://127.0.0.1:9450") as client:
        resp = await client.post("/api/steer", json={"prompt": "chimera at 0.73"})
    assert resp.status_code == want


async def test_tokenless_steer_refused_where_the_socket_owner_cannot_be_read(isolated_engine, monkeypatch):
    # Vulnetix GCVE-110-VULN-PYPI-2026-000643: without /proc/net/tcp (macOS, Windows) every
    # loopback caller passed. It is refused now, unless the operator opts in.
    import oracle_platon.main as main_mod

    monkeypatch.delenv("PLATON_STEER_TOKEN", raising=False)
    monkeypatch.delenv("PLATON_PUBLIC_WRITES", raising=False)
    monkeypatch.setattr(main_mod, "_PROC_NET_TCP", ())
    monkeypatch.delenv("PLATON_LOCAL_UNVERIFIED", raising=False)
    monkeypatch.delenv("PLATON_LOCAL_RELAY", raising=False)
    transport = ASGITransport(app=app, client=("127.0.0.1", 40000))
    async with AsyncClient(transport=transport, base_url="http://127.0.0.1:9450") as client:
        async def steer_status():
            return (await client.post("/api/steer", json={"prompt": "chimera at 0.73"})).status_code
        assert await steer_status() == 401
        monkeypatch.setenv("PLATON_LOCAL_UNVERIFIED", "1")
        assert await steer_status() == 401
        monkeypatch.setenv("PLATON_LOCAL_RELAY", "1")
        monkeypatch.delenv("PLATON_LOCAL_UNVERIFIED")
        assert await steer_status() == 401
        monkeypatch.setenv("PLATON_LOCAL_UNVERIFIED", "1")
        assert await steer_status() == 200


@pytest.mark.asyncio
async def test_production_steer_requires_token_despite_local_opt_ins(isolated_engine, monkeypatch):
    monkeypatch.setenv("AIFACTORY_PROD", "1")
    monkeypatch.setenv("PLATON_LOCAL_RELAY", "1")
    monkeypatch.setenv("PLATON_LOCAL_UNVERIFIED", "1")
    monkeypatch.setenv("PLATON_PUBLIC_WRITES", "1")
    monkeypatch.delenv("PLATON_STEER_TOKEN", raising=False)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://localhost") as client:
        assert (await client.post("/api/steer", json={"prompt": "x"})).status_code == 401
        monkeypatch.setenv("PLATON_STEER_TOKEN", "test-operator-secret")
        assert (await client.post("/api/steer", json={"prompt": "x"})).status_code == 401
        response = await client.post("/api/steer", json={"prompt": "x"},
                                     headers={"X-Platon-Token": "test-operator-secret"})
        assert response.status_code == 200


def test_trusted_proxies_are_loopback_unless_named(monkeypatch, tmp_path):
    # Vulnetix GCVE-110-VULN-PYPI-2026-000636: X-Real-IP / X-Forwarded-For were taken from any
    # private peer, so a neighbour on the same docker network or LAN named its own address.
    import ipaddress
    import oracle_platon.main as trust

    monkeypatch.delenv("PLATON_TRUSTED_PROXIES", raising=False)
    assert trust._peer_is_trusted_proxy("127.0.0.1") and trust._peer_is_trusted_proxy("::1")
    for neighbour in ("172.18.0.7", "10.0.0.5", "192.168.1.20", "fe80::1", "not-an-address", ""):
        assert not trust._peer_is_trusted_proxy(neighbour), neighbour
    monkeypatch.setenv("PLATON_TRUSTED_PROXIES", "10.1.0.0/16, 172.18.0.9")
    assert trust._peer_is_trusted_proxy("10.1.2.3") and trust._peer_is_trusted_proxy("172.18.0.9")
    assert not trust._peer_is_trusted_proxy("127.0.0.1")  # the list replaces the default
    route = tmp_path / "route"
    gateway_hex = "010012AC" if sys.byteorder == "little" else "AC120001"  # 172.18.0.1
    route.write_text("Iface\tDestination\tGateway\tFlags\n"
                     "eth0\t00000000\t" + gateway_hex + "\t0003\n")
    monkeypatch.setattr(trust, "_PROC_NET_ROUTE", str(route))
    monkeypatch.setenv("PLATON_TRUSTED_PROXIES", "gateway")
    assert trust._peer_is_trusted_proxy("172.18.0.1") and not trust._peer_is_trusted_proxy("172.18.0.2")
    named = {"frontend": (ipaddress.ip_address("172.18.0.5"),)}
    monkeypatch.setattr(trust, "_proxy_name_addresses", lambda name: named.get(name, ()))
    monkeypatch.setenv("PLATON_TRUSTED_PROXIES", "127.0.0.1, frontend")
    assert trust._peer_is_trusted_proxy("172.18.0.5") and not trust._peer_is_trusted_proxy("172.18.0.6")
