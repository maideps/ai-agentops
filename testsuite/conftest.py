"""Suite-wide guards: no outbound network outside tests marked ``live``."""

import ipaddress
import os
import socket
from collections.abc import Iterator
from pathlib import Path
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


@pytest.fixture
def blocked_network_attempts() -> list[str]:
    """Hosts the guard refused during the test, in order (request it to assert on them)."""
    return []


@pytest.fixture(autouse=True)
def block_network(
    request: pytest.FixtureRequest,
    monkeypatch: pytest.MonkeyPatch,
    blocked_network_attempts: list[str],
) -> Iterator[None]:
    if request.node.get_closest_marker("live"):
        yield
        return

    real_connect = socket.socket.connect
    real_connect_ex = socket.socket.connect_ex
    real_getaddrinfo = socket.getaddrinfo

    def _check(sock: socket.socket, address: Any) -> None:
        if sock.family in (socket.AF_INET, socket.AF_INET6) and not _is_loopback(address[0]):
            blocked_network_attempts.append(str(address[0]))
            raise NetworkAccessBlockedError(f"network access blocked in tests: {address[0]!r}")

    def guarded_connect(sock: socket.socket, address: Any) -> None:
        _check(sock, address)
        real_connect(sock, address)

    def guarded_connect_ex(sock: socket.socket, address: Any) -> int:
        _check(sock, address)
        return real_connect_ex(sock, address)

    def guarded_getaddrinfo(host: Any, *args: Any, **kwargs: Any) -> Any:
        if host is not None and not _is_loopback(host):
            blocked_network_attempts.append(host.decode() if isinstance(host, bytes) else str(host))
            raise NetworkAccessBlockedError(f"DNS lookup blocked in tests: {host!r}")
        return real_getaddrinfo(host, *args, **kwargs)

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    monkeypatch.setattr(socket.socket, "connect_ex", guarded_connect_ex)
    monkeypatch.setattr(socket, "getaddrinfo", guarded_getaddrinfo)
    yield


# Integration database (docker compose service "postgres", database agentops_test).
# Defaults match docker-compose.yml; override with the AGENTOPS_TEST_* variables.
DATASET_DIR = Path(__file__).resolve().parent.parent / "datasets" / "synthetic"


@pytest.fixture(scope="session")
def admin_dsn() -> str:
    return os.environ.get(
        "AGENTOPS_TEST_DATABASE_URL",
        "postgresql://agentops:change-me@127.0.0.1:15432/agentops_test",
    )


@pytest.fixture(scope="session")
def analytics_dsn() -> str:
    return os.environ.get(
        "AGENTOPS_TEST_ANALYTICS_URL",
        "postgresql://agentops_analytics:change-me-analytics@127.0.0.1:15432/agentops_test",
    )


@pytest.fixture(scope="session")
def app_dsn() -> str:
    """The tool gateway's least-privilege login (reads plus approvals, tickets, policy log)."""
    return os.environ.get(
        "AGENTOPS_TEST_APP_URL",
        "postgresql://agentops_app:change-me-app@127.0.0.1:15432/agentops_test",
    )


@pytest.fixture(scope="session")
def seeded_db(admin_dsn: str) -> str:
    """Migrate and seed agentops_test once per session; returns the admin DSN."""
    import psycopg

    from agentops_agents.checkpoints import setup_checkpoints
    from agentops_data.migrations import apply_migrations
    from agentops_data.seed import seed_dataset
    from agentops_retrieval.embedding import HashingEmbedder
    from agentops_retrieval.indexing import index_chunks

    with psycopg.connect(admin_dsn) as conn:
        apply_migrations(conn)
        seed_dataset(conn, DATASET_DIR)
        index_chunks(conn, HashingEmbedder())
    setup_checkpoints(admin_dsn)
    return admin_dsn


@pytest.fixture(scope="session")
def span_exporter() -> Any:
    """In-memory OpenTelemetry exporter behind the redaction layer, installed globally once."""
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    from agentops_telemetry.tracing import configure_tracing

    exporter = InMemorySpanExporter()
    configure_tracing(service_name="agentops-tests", exporter=exporter, set_global=True)
    return exporter


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
        "APP_DATABASE_URL",
        "ANALYTICS_DATABASE_URL",
        "MOCK_SCRIPTS_DIR",
        "DEMO_API_TOKEN",
        "DEMO_TENANT_ID",
        "DEMO_USER_ID",
        "LANGFUSE_ENABLED",
        # LangChain/LangSmith tracing would export run data; it stays off in tests.
        "LANGSMITH_TRACING",
        "LANGCHAIN_TRACING_V2",
    ):
        monkeypatch.delenv(name, raising=False)
