#!/usr/bin/env python3
"""Connect Platon to a real AIMarket hub and exercise the live flow.

Usage:
    PLATON_TESTING=1 python scripts/register_with_hub.py [hub_url]

Steps (each reported, failures are non-fatal so you see the full picture):
  1. Self-verify our signed manifest with the hub's 4-field canonical.
  2. Fetch the hub's /.well-known to confirm reachability + protocol.
  3. Attempt federation announce (admin-gated on the public demo -> reported).
  4. Open a demo payment channel (works live in demo_mode).
  5. Run an intent search for our randomness/oracle capabilities.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
os.environ.setdefault("PLATON_TESTING", "1")

from platon import hub_client  # noqa: E402
from platon.config import settings  # noqa: E402


def show(title: str, payload: object) -> None:
    print(f"\n=== {title} ===")
    print(json.dumps(payload, indent=2, ensure_ascii=False)[:1600])


async def main(hub_url: str) -> None:
    print(f"Platon public_url : {settings.public_url}")
    print(f"Target hub        : {hub_url}")

    show("1. self-verify our signed manifest", hub_client.self_verify_manifest())
    show("2. hub reachability (/.well-known)", await hub_client.hub_info(hub_url))
    show("3. federation announce", await hub_client.announce(hub_url))

    channel = await hub_client.open_channel(1.0, hub_url)
    show("4. open demo payment channel ($1.00)", channel)
    channel_id = ((channel.get("response") or {}).get("channel") or {}).get("channel_id")

    show(
        "5. search intent='verifiable randomness beacon'",
        await hub_client.search("verifiable randomness beacon", hub_url=hub_url),
    )
    # Platon as a market CONSUMER (real protocol call; demo hub may 402/503).
    show(
        "6. consume a capability THROUGH the hub (using the channel)",
        await hub_client.invoke_capability(
            "prod-platon", "platon.random@v1", {"num_bytes": 16}, channel_id, hub_url
        ),
    )


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else settings.hub_url
    asyncio.run(main(target))
