"""Suite-wide guards: no outbound network outside tests marked ``live``."""

import ipaddress
import socket
from collections.abc import Iterator
from typing import Any

import pytest

_LOOPBACK_NAMES = {"localhost", "localhost.localdomain"}


class NetworkAccessBlockedError(RuntimeError):
    """Raised when a non-live test tries to reach a non-loopback address."""


def _is_loopback(host: object) -> bool:
    if isinstance(host, bytes):
        host = host.decode()
    if not isinstance(host, str):
        return False
    if host.lower() in _LOOPBACK_NAMES:
        return True
    try:
        return ipaddress.ip_address(host.split("%", 1)[0]).is_loopback
    except ValueError:
        return False


@pytest.fixture(autouse=True)
def block_network(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> Iterator[None]:
    if request.node.get_closest_marker("live"):
        yield
        return

    real_connect = socket.socket.connect
    real_connect_ex = socket.socket.connect_ex
    real_getaddrinfo = socket.getaddrinfo

    def _check(sock: socket.socket, address: Any) -> None:
        if sock.family in (socket.AF_INET, socket.AF_INET6) and not _is_loopback(address[0]):
            raise NetworkAccessBlockedError(f"network access blocked in tests: {address[0]!r}")

    def guarded_connect(sock: socket.socket, address: Any) -> None:
        _check(sock, address)
        real_connect(sock, address)

    def guarded_connect_ex(sock: socket.socket, address: Any) -> int:
        _check(sock, address)
        return real_connect_ex(sock, address)

    def guarded_getaddrinfo(host: Any, *args: Any, **kwargs: Any) -> Any:
        if host is not None and not _is_loopback(host):
            raise NetworkAccessBlockedError(f"DNS lookup blocked in tests: {host!r}")
        return real_getaddrinfo(host, *args, **kwargs)

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    monkeypatch.setattr(socket.socket, "connect_ex", guarded_connect_ex)
    monkeypatch.setattr(socket, "getaddrinfo", guarded_getaddrinfo)
    yield


@pytest.fixture(autouse=True)
def isolate_settings_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep a developer's real environment (LLM_MODE, keys, DATABASE_URL) out of tests."""
    for name in (
        "APP_ENV",
        "LOG_LEVEL",
        "LLM_MODE",
        "ENABLE_LIVE_LLM",
        "LLM_PROVIDER",
        "LLM_MODEL",
        "MAX_LLM_CALLS_PER_RUN",
        "MAX_TOOL_CALLS_PER_RUN",
        "MAX_GRAPH_STEPS",
        "MAX_RUN_SECONDS",
        "MAX_OUTPUT_TOKENS",
        "MAX_REQUESTS_PER_DEMO_USER",
        "DATABASE_URL",
        "LANGFUSE_ENABLED",
    ):
        monkeypatch.delenv(name, raising=False)
