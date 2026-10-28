"""FastAPI application — simulation, WebSocket, AIMarket."""

from __future__ import annotations

import asyncio
import hmac
import ipaddress
import os
import socket
import sys
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from starlette.requests import HTTPConnection
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from oracle_platon.aimarket import invoke, manifest, well_known
from oracle_platon.config import settings
from oracle_platon.simulation import engine


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

# AIMarket capabilities that mutate the shared simulation engine. Invoking these
# via /ai-market/v2/invoke must clear the same write-gate + tighter rate limiter
# as /api/steer, /api/project and /ws; every other capability is read-only.
_MUTATING_CAPABILITIES = frozenset({"platon.steer@v1", "platon.project@v1"})

# Write-gate on every state-mutating call; the read-only surface is unchanged.
# With PLATON_STEER_TOKEN set, a call needs that shared secret (HTTP header
# ``X-Platon-Token`` / WS message ``token``). Without it, production refuses every
# write and any other environment takes writes from this machine only (see
# _write_authorized). Up to 0.1.3 a keyless server took writes from anyone. A public
# demo, where every visitor steers, says so with PLATON_PUBLIC_WRITES=1.
def _steer_token() -> str:
    """Read per request, not once at import.

    A token exported after the process started (or injected by an orchestrator into an
    already-running container) used to have no effect at all, which made the gate look
    configured while it was inert.
    """
    return (os.environ.get("PLATON_STEER_TOKEN") or "").strip()


# Which TCP peers may name the caller through X-Real-IP / X-Forwarded-For. Loopback only by default:
# trusting every private address let any neighbour on the same docker network or LAN send its own
# (Vulnetix GCVE-110-VULN-PYPI-2026-000636). PLATON_TRUSTED_PROXIES is a comma list of addresses,
# CIDRs, host names (a compose service such as the frontend's nginx, looked up again every minute)
# and `gateway` (this container's default route: the host's nginx, when the port is published on the
# host).
_TRUSTED_PROXIES_DEFAULT = "127.0.0.1/32,::1/128"
_PROXY_NAME_TTL = 60.0
_PROC_NET_ROUTE = "/proc/net/route"
_proxy_names: dict[str, tuple[float, tuple]] = {}


def _default_gateway() -> str | None:
    """The IPv4 default route's gateway, from /proc/net/route (Linux), or None."""
    try:
        with open(_PROC_NET_ROUTE, encoding="ascii", errors="replace") as fh:
            next(fh, None)  # the header line
            for line in fh:
                f = line.split()
                if len(f) > 2 and f[1] == "00000000":
                    raw = bytes.fromhex(f[2])
                    return str(ipaddress.IPv4Address(raw[::-1] if sys.byteorder == "little" else raw))
    except (OSError, ValueError):
        return None
    return None


def _proxy_name_addresses(name: str) -> tuple:
    now = time.monotonic()
    hit = _proxy_names.get(name)
    if hit and now - hit[0] < _PROXY_NAME_TTL:
        return hit[1]
    try:
        found = {ipaddress.ip_address(info[4][0].split("%")[0])
                 for info in socket.getaddrinfo(name, None, proto=socket.IPPROTO_TCP)}
    except (OSError, ValueError):
        found = set()
    addrs = tuple(sorted(found, key=str))
    _proxy_names[name] = (now, addrs)
    return addrs


def _peer_is_trusted_proxy(peer: str) -> bool:
    """Is the TCP peer one of PLATON_TRUSTED_PROXIES?"""
    try:
        addr = ipaddress.ip_address((peer or "").split("%")[0])
    except ValueError:
        return False
    if addr.version == 6 and addr.ipv4_mapped:
        addr = addr.ipv4_mapped
    raw = os.environ.get("PLATON_TRUSTED_PROXIES")
    for entry in (_TRUSTED_PROXIES_DEFAULT if raw is None else raw).split(","):
        entry = entry.strip()
        if not entry:
            continue
        if entry == "gateway":
            gateway = _default_gateway()
            if gateway and addr == ipaddress.ip_address(gateway):
                return True
            continue
        try:
            if addr in ipaddress.ip_network(entry, strict=False):
                return True
            continue
        except ValueError:
            pass
        if addr in _proxy_name_addresses(entry):
            return True
    return False


def _from_trusted_proxy(peer: str) -> bool:
    """Is the TCP peer our own nginx (PLATON_TRUSTED_PROXIES)? Only then are X-Real-IP /
    X-Forwarded-For the caller's: anyone reaching the port another way writes them itself, a fresh
    LLM-steer budget per request."""
    return _peer_is_trusted_proxy(peer)


def _key_from(headers, peer: str) -> str:
    if _from_trusted_proxy(peer):
        xri = (headers.get("x-real-ip") or "").strip()
        if xri:
            return xri
        # RIGHT-most hop: nginx appends the real peer, the left entry is caller-typed. This
        # keys the LLM-steer budget, so a forgeable key was an unbounded spend.
        hops = [h.strip() for h in (headers.get("x-forwarded-for") or "").split(",") if h.strip()]
        if hops:
            return hops[-1]
    return peer or "*"


def _client_key(request: Request) -> str:
    return _key_from(request.headers, request.client.host if request.client else "")


def _ws_client_key(ws: WebSocket) -> str:
    return _key_from(ws.headers, ws.client.host if ws.client else "")


_LOOPBACK_NAMES = frozenset({"localhost", "127.0.0.1", "::1"})
_FORWARDING_HEADERS = ("x-forwarded-for", "x-real-ip", "forwarded", "x-forwarded-host")

# The kernel's tables of TCP sockets, with the uid that owns each (Linux).
_PROC_NET_TCP = ("/proc/net/tcp", "/proc/net/tcp6")


def _proc_endpoint(field: str) -> tuple[str, int]:
    """`0100007F:1F90` -> ("127.0.0.1", 8080): each 32-bit word of the address is printed in
    the kernel's byte order, the port in plain hex."""
    hexaddr, _, hexport = field.partition(":")
    raw = bytes.fromhex(hexaddr)
    if sys.byteorder == "little":
        raw = b"".join(raw[i:i + 4][::-1] for i in range(0, len(raw), 4))
    addr = ipaddress.ip_address(raw)
    if addr.version == 6 and addr.ipv4_mapped:
        addr = addr.ipv4_mapped
    return str(addr), int(hexport, 16)


def _flag(name: str) -> bool:
    return (os.environ.get(name) or "").strip().lower() in ("1", "true", "yes", "on")


def _caller_is_this_user(conn: HTTPConnection) -> bool:
    """Allow explicitly trusted local TCP callers whose socket belongs to this user.

    TCP ownership cannot distinguish a direct client from an arbitrary same-user relay:
    a worker may hold no listener and its program name proves nothing. Therefore keyless
    TCP is refused unless PLATON_LOCAL_RELAY=1 explicitly trusts that boundary
    (GCVE-110-VULN-PYPI-2026-000643). Without a socket table, the additional
    PLATON_LOCAL_UNVERIFIED=1 opt-in is required. A known different owner or an
    unmatched connection is always refused. Prefer a configured token to either opt-in.
    """
    if not _flag("PLATON_LOCAL_RELAY"):
        return False
    tables = [p for p in _PROC_NET_TCP if os.path.exists(p)]
    if not tables:
        return _flag("PLATON_LOCAL_UNVERIFIED")
    client = conn.client
    if not client:
        return False
    try:
        peer = ipaddress.ip_address(client.host)
    except ValueError:
        return False
    if peer.version == 6 and peer.ipv4_mapped:
        peer = peer.ipv4_mapped
    want = (str(peer), int(client.port or 0))
    server_port = (conn.scope.get("server") or (None, None))[1]
    for path in tables:
        try:
            with open(path, encoding="ascii", errors="replace") as fh:
                next(fh, None)  # the header line
                for line in fh:
                    f = line.split()
                    if len(f) < 10 or f[3] != "01":  # 01 = ESTABLISHED
                        continue
                    try:
                        if _proc_endpoint(f[1]) != want:
                            continue
                        if server_port is not None and _proc_endpoint(f[2])[1] != int(server_port):
                            continue
                        if int(f[7]) != os.geteuid():
                            return False
                        return True
                    except ValueError:
                        continue
        except OSError:
            continue
    return False


def _host_is_loopback(hostport: str) -> bool:
    """`localhost[:port]`, `127.0.0.1[:port]` or `[::1][:port]`, as a Host header or netloc."""
    value = hostport.strip().lower()
    if value.startswith("["):
        host = value[1:value.find("]")] if "]" in value else ""
    else:
        host = value.rsplit(":", 1)[0] if value.count(":") == 1 else value
    return host in _LOOPBACK_NAMES


def _local_caller(conn: HTTPConnection) -> bool:
    """Explicitly trusted keyless loopback TCP, with local Host/Origin and no
    forwarding headers. Socket ownership still must match, unless separately opted out.
    """
    peer = conn.client.host if conn.client else ""
    try:
        if not ipaddress.ip_address(peer).is_loopback:
            return False
    except ValueError:
        return False
    if any(h in conn.headers for h in _FORWARDING_HEADERS):
        return False
    if not _host_is_loopback(conn.headers.get("host", "")):
        return False
    origin = conn.headers.get("origin")
    if origin is not None:
        scheme, _, rest = origin.strip().partition("://")
        if scheme not in ("http", "https") or not _host_is_loopback(rest.split("/", 1)[0]):
            return False
    return _caller_is_this_user(conn)


def _write_authorized(token: str | None, conn: HTTPConnection) -> bool:
    """True when state-mutating writes are permitted for this request."""
    steer_token = _steer_token()
    if not steer_token:
        # Fail-closed in production: refuse writes when no steer token is
        # configured. A missing token in production must not leave mutating
        # endpoints (incl. the /ai-market invoke steer/project capabilities) open.
        import os as _os

        env = (_os.environ.get("AIFACTORY_ENV") or "").strip().lower()
        prod = (
            env in ("production", "prod", "live")
            or (_os.environ.get("AIFACTORY_PROD") or "").strip().lower() in ("1", "true", "yes", "on")
            or (_os.environ.get("AIFACTORY_PRODUCTION") or "").strip().lower() in ("1", "true", "yes", "on")
        )
        if prod:
            return False
        # No token outside production: only explicitly trusted local TCP. Any caller used to
        # steer the world here, and the server binds 0.0.0.0 (the class of Vulnetix
        # GCVE-110-PYPI-2026-018883, CWE-306). A public demo, where every visitor and the
        # hub's platon.steer@v1 steer the world, says so with PLATON_PUBLIC_WRITES=1.
        if (os.environ.get("PLATON_PUBLIC_WRITES") or "").strip().lower() in ("1", "true", "yes", "on"):
            return True
        return _local_caller(conn)
    return bool(token) and hmac.compare_digest(token, steer_token)


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
    from oracle_platon.oracle import oracle_info

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
    from oracle_platon import hub_client

    return {
        "hub_url": settings.hub_url,
        "manifest": hub_client.self_verify_manifest(),
        "hub": await hub_client.hub_info(),
    }


@app.post("/api/steer")
async def steer(req: SteerRequest, request: Request) -> dict[str, Any]:
    if not _write_authorized(request.headers.get("x-platon-token"), request):
        raise HTTPException(status_code=401, detail="write token required")
    if not _steer_limiter.allow(_client_key(request)):
        raise HTTPException(status_code=429, detail="rate limited")
    result = engine.steer(req.prompt)
    await manager.broadcast({"type": "steer", "data": result})
    return result


@app.post("/api/project")
async def project(req: ProjectRequest, request: Request) -> dict[str, float]:
    if not _write_authorized(request.headers.get("x-platon-token"), request):
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
    from oracle_platon.ask import answer

    if not _ask_limiter.allow(_client_key(request)):
        raise HTTPException(status_code=429, detail="rate limited")
    return await answer(req.question, req.lang, engine)


@app.get("/api/beacon")
async def beacon_feed(limit: int = 20) -> dict[str, Any]:
    """Recent hash-chained beacon rounds + an integrity-verification flag."""
    from oracle_platon.aimarket import beacon
    from oracle_platon.randomness import verify_beacon_chain

    rounds = list(beacon.rounds)
    # `beacon.rounds` is a bounded rolling window (deque) that legitimately drops
    # the genesis round after enough emits, so this operator self-check is a
    # linkage/entropy integrity check, not a genesis-anchored completeness proof.
    # External consumers verifying a chain should use the default (strict) mode.
    return {
        "rounds": rounds[-limit:],
        "chain_length": len(rounds),
        "chain_valid": verify_beacon_chain(rounds, require_genesis=False) if rounds else True,
    }


@app.post("/api/beacon/checkpoint")
async def beacon_checkpoint() -> dict[str, Any]:
    """Sign a commitment to the chain head; if an anchor webhook is configured,
    push it to that external transparency log (fire-and-forget)."""
    from oracle_platon.aimarket import beacon, utc_now_z

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
    if req.capability_id in _MUTATING_CAPABILITIES:
        # Same fail-closed write-lock as /api/steer and /api/project.
        if not _write_authorized(request.headers.get("x-platon-token"), request):
            raise HTTPException(status_code=401, detail="write token required")
        if not _steer_limiter.allow(_client_key(request)):
            raise HTTPException(status_code=429, detail="rate limited")
    elif not _invoke_limiter.allow(_client_key(request)):
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
                if not _write_authorized(raw.get("token"), ws):
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
                if not _write_authorized(raw.get("token"), ws):
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
        "oracle_platon.main:app",
        host=settings.host,
        port=settings.port,
        reload=False,
    )


if __name__ == "__main__":
    main()
