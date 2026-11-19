"""feat-002: /health/ready reports the database dependency without leaking its URL."""

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from agentops_api.app import create_app
from agentops_api.settings import Settings


def test_unreachable_database_makes_the_service_not_ready() -> None:
    url = "postgresql://agentops:CANARY-SECRET-0007@127.0.0.1:1/agentops"
    client = TestClient(create_app(Settings(database_url=SecretStr(url))))

    response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "not_ready", "checks": {"database": "failed"}}
    assert "CANARY-SECRET" not in response.text


@pytest.mark.integration
def test_reachable_database_is_reported_ok(seeded_db: str) -> None:
    client = TestClient(create_app(Settings(database_url=SecretStr(seeded_db))))

    response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready", "checks": {"database": "ok"}}
