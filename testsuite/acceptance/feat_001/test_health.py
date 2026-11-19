"""feat-001 (M0.1, FR-001 partial): health endpoints served by the app factory."""

from fastapi.testclient import TestClient

from agentops_api.app import create_app
from agentops_api.settings import Settings


def _client() -> TestClient:
    return TestClient(create_app(Settings()))


def test_live_returns_ok() -> None:
    response = _client().get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ready_returns_ready_with_empty_dependency_map() -> None:
    response = _client().get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready", "checks": {}}


def test_health_endpoints_reject_writes() -> None:
    assert _client().post("/health/live").status_code == 405
