"""Landauer FastAPI app — the whole AIMarket v2 surface comes from oracle-core."""

from __future__ import annotations

import os

from oracle_core import create_app

from landauer.capabilities import SPEC

app = create_app(SPEC, cors_origins=os.environ.get("LANDAUER_CORS_ORIGINS", "*"))


def main() -> None:
    import uvicorn

    uvicorn.run("landauer.main:app", host="0.0.0.0", port=int(os.environ.get("LANDAUER_PORT", "9309")), reload=False)


if __name__ == "__main__":
    main()
