import os

import pytest

os.environ.setdefault("PLATON_TESTING", "1")


@pytest.fixture(autouse=True)
def _no_kernel_socket_table(monkeypatch):
    """The tests fake loopback callers that are not real sockets, so the kernel's table would
    never show them on Linux. Each test sees what macOS sees, no table, unless it sets one."""
    import oracle_platon.main as _m

    monkeypatch.setattr(_m, "_PROC_NET_TCP", ())
