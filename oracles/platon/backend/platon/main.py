"""FastAPI application — simulation, WebSocket, AIMarket."""

from __future__ import annotations

import asyncio
import hmac
import os
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from platon.aimarket import invoke, manifest, well_known
from platon.config import settings
from platon.simulation import engine


class SteerRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=500)


class ProjectRequest(BaseModel):
    theta1: float
    theta2: float


class InvokeRequest(BaseModel):
    capability_id: str
    input: dict[str, Any] = Field(default_factory=dict)


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    lang: str = "en"


class _RateLimiter:
    """Tiny fixed-window limiter, keyed per client.

    Keyed by the real client IP (supplied by the reverse proxy) so one noisy
    client cannot consume the whole budget — and so the simulation's shared
    state cannot be driven by a single source flooding /api/steer or the socket.
    """

    def __init__(self, limit: int, window_s: float, *, max_keys: int = 8192) -> None:
        self.limit = limit
        self.window = window_s
        self.max_keys = max_keys
        self._buckets: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str = "*") -> bool:
        now = time.monotonic()
        if len(self._buckets) > self.max_keys:
            stale = [k for k, h in self._buckets.items() if not h or now - h[-1] > self.window]
            for k in stale:
                del self._buckets[k]
        hits = self._buckets[key]
        while hits and now - hits[0] > self.window:
            hits.popleft()
        if len(hits) >= self.limit:
            return False
        hits.append(now)
        return True


_ask_limiter = _RateLimiter(limit=30, window_s=60.0)
_invoke_limiter = _RateLimiter(limit=120, window_s=60.0)
_dream_limiter = _RateLimiter(limit=60, window_s=60.0)
# Mutations of the shared simulation state are the cheapest way to grief other
# viewers, so bound them per client too (previously unlimited).
_steer_limiter = _RateLimiter(limit=30, window_s=60.0)
_project_limiter = _RateLimiter(limit=60, window_s=60.0)

# Optional write-gate. The cave is a public, anonymous demo by design, so this is
# OFF by default (fail-open). Set PLATON_STEER_TOKEN to require a shared secret on
# every state-mutating call (HTTP header ``X-Platon-Token`` / WS message ``token``)
# without changing the read-only surface.
_STEER_TOKEN = (os.environ.get("PLATON_STEER_TOKEN") or "").strip()


def _client_key(request: Request) -> str:
    xri = (request.headers.get("x-real-ip") or "").strip()
    if xri:
        return xri
    xff = (request.headers.get("x-forwarded-for") or "").strip()
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "*"


def _ws_client_key(ws: WebSocket) -> str:
    xri = (ws.headers.get("x-real-ip") or "").strip()
    if xri:
        return xri
    xff = (ws.headers.get("x-forwarded-for") or "").strip()
    if xff:
        return xff.split(",")[0].strip()
    return ws.client.host if ws.client else "*"


def _write_authorized(token: str | None) -> bool:
    """True when state-mutating writes are permitted for this request."""
    if not _STEER_TOKEN:
        return True  # public demo — no token configured
    return bool(token) and hmac.compare_digest(token, _STEER_TOKEN)


class ConnectionManager:
    def __init__(self) -> None:
        self.active: list[WebSocket] = []

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self.active.append(ws)
        engine.viewers = len(self.active)

    def disconnect(self, ws: WebSocket) -> None:
        if ws in self.active:
            self.active.remove(ws)
        engine.viewers = len(self.active)

    async def broadcast(self, message: dict[str, Any]) -> None:
        dead: list[WebSocket] = []
        for ws in self.active:
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


manager = ConnectionManager()
_sim_task: asyncio.Task | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _sim_task

    async def tick_loop() -> None:
        await asyncio.sleep(0)  # let lifespan yield before first heavy tick
        while True:
            event = await engine.advance()
            payload = {"type": "state", "data": engine.telemetry()}
            await manager.broadcast(payload)
            if event:
                await manager.broadcast({"type": "event", "data": event})
            await asyncio.sleep(1.0 / settings.tick_hz)

    if not os.environ.get("PLATON_TESTING"):
        _sim_task = asyncio.create_task(tick_loop())
    yield
    engine.stop()
    if _sim_task:
        _sim_task.cancel()


app = FastAPI(
    title="Platon UMBRAL",
    description="32D dynamical shadow oracle",
    version="0.1.0",
    lifespan=lifespan,
)

_origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()] or ["*"]
_allow_all = _origins == ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    # Credentials cannot be combined with the "*" wildcard (CORS spec); only
    # enable them when explicit origins are configured.
    allow_credentials=not _allow_all,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health() -> dict[str, Any]:
    from platon.oracle import oracle_info

    return {
        "status": "ok",
        "tick": engine.tick,
        "viewers": engine.viewers,
        "kappa": engine.state.kappa,
        "order_parameter": engine.state.order_parameter(),
        "oracle": oracle_info(),
    }


@app.get("/api/state")
async def get_state() -> dict[str, Any]:
    return engine.telemetry()


@app.get("/api/hub/status")
async def hub_status() -> dict[str, Any]:
    """Federation posture: our manifest self-check + live hub reachability."""
    from platon import hub_client

    return {
        "hub_url": settings.hub_url,
        "manifest": hub_client.self_verify_manifest(),
        "hub": await hub_client.hub_info(),
    }


@app.post("/api/steer")
async def steer(req: SteerRequest, request: Request) -> dict[str, Any]:
    if not _write_authorized(request.headers.get("x-platon-token")):
        raise HTTPException(status_code=401, detail="write token required")
    if not _steer_limiter.allow(_client_key(request)):
        raise HTTPException(status_code=429, detail="rate limited")
    result = engine.steer(req.prompt)
    await manager.broadcast({"type": "steer", "data": result})
    return result


@app.post("/api/project")
async def project(req: ProjectRequest, request: Request) -> dict[str, float]:
    if not _write_authorized(request.headers.get("x-platon-token")):
        raise HTTPException(status_code=401, detail="write token required")
    if not _project_limiter.allow(_client_key(request)):
        raise HTTPException(status_code=429, detail="rate limited")
    return engine.set_projection(req.theta1, req.theta2)


@app.get("/api/dream")
async def dream(request: Request, steps: int = 60) -> dict[str, Any]:
    if not _dream_limiter.allow(_client_key(request)):
        raise HTTPException(status_code=429, detail="rate limited")
    return engine.dream(steps=min(max(steps, 10), 120))


@app.post("/api/ask")
async def ask(req: AskRequest, request: Request) -> dict[str, Any]:
    """Grounded, read-only informational guide (localized)."""
    from platon.ask import answer

    if not _ask_limiter.allow(_client_key(request)):
        raise HTTPException(status_code=429, detail="rate limited")
    return await answer(req.question, req.lang, engine)


@app.get("/api/beacon")
async def beacon_feed(limit: int = 20) -> dict[str, Any]:
    """Recent hash-chained beacon rounds + an integrity-verification flag."""
    from platon.aimarket import beacon
    from platon.randomness import verify_beacon_chain

    rounds = list(beacon.rounds)
    return {
        "rounds": rounds[-limit:],
        "chain_length": len(rounds),
        "chain_valid": verify_beacon_chain(rounds) if rounds else True,
    }


@app.post("/api/beacon/checkpoint")
async def beacon_checkpoint() -> dict[str, Any]:
    """Sign a commitment to the chain head; if an anchor webhook is configured,
    push it to that external transparency log (fire-and-forget)."""
    from platon.aimarket import beacon
    from platon.aimarket import utc_now_z

    cp = beacon.checkpoint(utc_now_z())
    if settings.beacon_anchor_webhook:
        try:
            import httpx

            async with httpx.AsyncClient(timeout=5.0) as client:
                await client.post(settings.beacon_anchor_webhook, json=cp)
            cp["anchored"] = True
        except Exception:
            cp["anchored"] = False
    return cp


@app.get("/api/witnesses")
async def witnesses(limit: int = 20) -> dict[str, Any]:
    return {
        "witnesses": [
            {
                "event": w.event,
                "text": w.text,
                "source": w.source,
                "model": w.model,
                "timestamp": w.timestamp,
            }
            for w in list(engine.witnesses)[:limit]
        ]
    }


@app.get("/api/activity")
async def activity(limit: int = 50) -> dict[str, Any]:
    return {"activity": list(engine.activity)[:limit]}


# --- AIMarket Protocol v2 ---

@app.get("/.well-known/ai-market.json")
async def ai_market_well_known() -> dict[str, Any]:
    return well_known()


@app.get("/ai-market/v2/manifest")
async def ai_market_manifest() -> dict[str, Any]:
    return manifest()


@app.post("/ai-market/v2/invoke")
async def ai_market_invoke(req: InvokeRequest, request: Request) -> dict[str, Any]:
    if not _invoke_limiter.allow(_client_key(request)):
        raise HTTPException(status_code=429, detail="rate limited")
    try:
        result = await invoke(req.capability_id, req.input)
        record = engine.log_agent_invoke(
            req.capability_id, req.input, result, source="aimarket-agent"
        )
        await manager.broadcast({"type": "agent_invoke", "data": record})
        if record.get("prediction") and req.capability_id == "platon.dream@v1":
            await manager.broadcast(
                {"type": "dream", "data": record["prediction"], "source": "agent"}
            )
        return {"ok": True, **result}
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    await manager.connect(ws)
    key = _ws_client_key(ws)
    try:
        await ws.send_json({"type": "state", "data": engine.telemetry()})
        while True:
            raw = await ws.receive_json()
            if not isinstance(raw, dict):
                await ws.send_json({"type": "error", "error": "malformed message"})
                continue
            msg_type = raw.get("type")

            if msg_type == "steer":
                if not _write_authorized(raw.get("token")):
                    await ws.send_json({"type": "error", "error": "write token required"})
                    continue
                if not _steer_limiter.allow(key):
                    await ws.send_json({"type": "error", "error": "rate limited"})
                    continue
                prompt = raw.get("prompt")
                if not isinstance(prompt, str) or not prompt.strip():
                    await ws.send_json({"type": "error", "error": "prompt required"})
                    continue
                result = engine.steer(prompt[:500])
                await ws.send_json({"type": "steer", "data": result})

            elif msg_type == "project":
                if not _write_authorized(raw.get("token")):
                    await ws.send_json({"type": "error", "error": "write token required"})
                    continue
                if not _project_limiter.allow(key):
                    await ws.send_json({"type": "error", "error": "rate limited"})
                    continue
                try:
                    theta1 = float(raw["theta1"])
                    theta2 = float(raw["theta2"])
                except (KeyError, TypeError, ValueError):
                    await ws.send_json({"type": "error", "error": "theta1/theta2 must be numbers"})
                    continue
                result = engine.set_projection(theta1, theta2)
                await ws.send_json({"type": "project", "data": result})

            elif msg_type == "dream":
                if not _dream_limiter.allow(key):
                    await ws.send_json({"type": "error", "error": "rate limited"})
                    continue
                try:
                    steps = int(raw.get("steps", 60))
                except (TypeError, ValueError):
                    steps = 60
                result = engine.dream(steps=min(max(steps, 10), 120))
                await ws.send_json({"type": "dream", "data": result, "source": "human"})
                await manager.broadcast({"type": "dream", "data": result, "source": "human"})

            else:
                await ws.send_json({"type": "error", "error": f"unknown message type: {msg_type!r}"})
    except WebSocketDisconnect:
        pass
    except Exception:
        # Never let a malformed frame leak the connection from the manager.
        try:
            await ws.close()
        except Exception:
            pass
    finally:
        manager.disconnect(ws)


def main() -> None:
    import uvicorn

    uvicorn.run(
        "platon.main:app",
        host=settings.host,
        port=settings.port,
        reload=False,
    )


if __name__ == "__main__":
    main()
