"""Gauss FastAPI app — the whole AIMarket v2 surface comes from oracle-core."""

from __future__ import annotations

import os

from oracle_core import create_app

from gauss.capabilities import SPEC

app = create_app(SPEC, cors_origins=os.environ.get("GAUSS_CORS_ORIGINS", "*"))


def main() -> None:
    import uvicorn

    uvicorn.run("gauss.main:app", host="0.0.0.0", port=int(os.environ.get("GAUSS_PORT", "9311")), reload=False)


if __name__ == "__main__":
    main()
