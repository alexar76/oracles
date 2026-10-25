import pytest
from httpx import ASGITransport, AsyncClient

from oracle_platon.main import app
from oracle_platon.randomness import verify_randomness
from oracle_platon.signing import Signer
from oracle_platon.simulation import SimulationEngine


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
