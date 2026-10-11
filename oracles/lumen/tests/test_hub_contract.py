"""Contract: whatever trust graph the HUB builds, the real LUMEN must be able to score it.

The hub's tests mock LUMEN and LUMEN's tests feed it hand-made graphs, so nothing checked the
seam between them. From 2026-09-26 one invoke failure (a -0.25 edge) made every request the hub
sent fail LUMEN's "trust weight must be non-negative", which the hub reads as an oracle outage:
every new publisher on modelmarket.dev was scored untrusted, hidden from search and refused at
invoke, for a week.

This drives the hub's real path — HubDatabase, SupplySecurity.record_invoke / slash edges,
refresh_publisher_trust → LumenTrustClient — and answers the client's HTTP call with LUMEN's own
`pagerank.run`, exactly as the oracle's invoke endpoint would. Runs in the oracles venv (numpy);
the hub is imported from the monorepo.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[4]
sys.path[:0] = [str(ROOT / "aimarket-hub"), str(Path(__file__).resolve().parents[1])]

# Hard imports, never importorskip: a contract test that skips when one side is missing
# reports green over the exact seam it exists to check.
from aimarket_hub import database as hub_db  # noqa: E402
from aimarket_hub import lumen_client  # noqa: E402
from aimarket_hub import supply_security  # noqa: E402
from aimarket_hub.config import HubConfig  # noqa: E402
from lumen import pagerank  # noqa: E402


@pytest.fixture()
def security(tmp_path, monkeypatch):
    monkeypatch.setenv("AIMARKET_ORACLE_FAMILY_URL", "https://lumen.contract.test/family")
    real_client = httpx.Client
    calls = []

    def lumen(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["capability_id"] == "lumen.reputation@v1"
        calls.append(body["input"])
        try:
            out = pagerank.run(body["input"])          # LUMEN's own handler
        except ValueError as exc:                       # what the oracle answers on bad input
            return httpx.Response(200, json={"ok": False, "error": str(exc)})
        return httpx.Response(200, json={"ok": True, "output": out})

    monkeypatch.setattr(lumen_client.httpx, "Client",
                        lambda **kw: real_client(transport=httpx.MockTransport(lumen)))
    db = hub_db.HubDatabase(tmp_path / "hub.db")
    sec = supply_security.SupplySecurity(db, HubConfig())
    sec._lumen_calls = calls
    return sec


def _history(sec, publisher: str) -> None:
    """Every kind of edge the hub writes: successes, failures, a verified failure, a slash."""
    for ok in (True, True, False, False, True, True, True, True):
        sec.record_invoke(publisher_id=publisher, consumer_id="consumer:anonymous", success=ok,
                          product_id="p", capability_id="c@v1")
    sec.db.trust_add_edge("consumer:x", publisher, -0.25, "verified_failure")
    sec.db.trust_add_edge(supply_security._HUB_ANCHOR, "bad-publisher", supply_security._SLASH_EDGE_WEIGHT, "slash")


def test_a_new_publisher_is_scored_on_a_graph_with_penalties(security):
    _history(security, "old-publisher")
    score = security.refresh_publisher_trust("new-publisher")
    assert security._lumen_calls, "the hub never asked LUMEN"
    assert all(e[2] >= 0 for call in security._lumen_calls for e in call["edges"])
    assert security._lumen_health.get("new-publisher") is True, "LUMEN refused the hub's graph"
    assert score >= security.policy.min_trust_discover, "a new publisher must be discoverable"


def test_the_publisher_with_history_gets_a_healthy_score(security):
    _history(security, "old-publisher")
    score = security.refresh_publisher_trust("old-publisher")
    assert security._lumen_health.get("old-publisher") is True
    assert 0.0 <= score <= 1.0
