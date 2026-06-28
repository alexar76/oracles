"""Lattice FastAPI app — the whole AIMarket v2 surface comes from oracle-core."""

from __future__ import annotations

import os

from oracle_core import create_app

from lattice.capabilities import SPEC

app = create_app(SPEC, cors_origins=os.environ.get("LATTICE_CORS_ORIGINS", "*"))


def main() -> None:
    import uvicorn

    uvicorn.run(
        "lattice.main:app",
        host="0.0.0.0",
        port=int(os.environ.get("LATTICE_PORT", "9301")),
        reload=False,
    )


if __name__ == "__main__":
    main()
