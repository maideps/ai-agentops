"""feat-009: optional live mode is authenticated and capped. POST /v1/runs runs a task for the
demo user, in mock mode by default (scripted model turns); hosted models need the existing
opt-in (D-005). Each demo user gets MAX_REQUESTS_PER_DEMO_USER runs per day."""

import uuid

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from agentops_api.app import create_app
from agentops_api.settings import Settings

TOKEN = "CANARY-SECRET-0130"  # noqa: S105 - a canary, not a credential


def _client(
    analytics_dsn: str | None, app_dsn: str | None, *, cap: int = 2, user: str = "user-a-analyst"
) -> TestClient:
    settings = Settings(
        database_url=None,
        app_database_url=SecretStr(app_dsn) if app_dsn else None,
        analytics_database_url=SecretStr(analytics_dsn) if analytics_dsn else None,
        demo_api_token=SecretStr(TOKEN),
        demo_tenant_id="demo-a",
        demo_user_id=user,
        max_requests_per_demo_user=cap,
    )
    return TestClient(create_app(settings))


def _auth() -> dict[str, str]:
    return {"Authorization": f"Bearer {TOKEN}"}


BODY = {"task_text": "Analyze the largest Q3 declines.", "script": "run-sample-q3-declines"}


def test_live_runs_need_the_demo_token() -> None:
    response = _client(None, None).post("/v1/runs", json=BODY)

    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHENTICATED"


@pytest.mark.integration
def test_an_authenticated_run_executes_and_returns_its_run_detail(
    seeded_db: str, analytics_dsn: str, app_dsn: str
) -> None:
    client = _client(analytics_dsn, app_dsn, cap=1000, user="user-a-admin")

    response = client.post("/v1/runs", json=BODY, headers=_auth())

    assert response.status_code == 201
    detail = response.json()
    assert detail["status"] == "completed"
    assert detail["llm_provider"] == "mock"
    assert [row["product_id"] for row in detail["analytics"]["declines"]] == [101, 102, 103]
    assert TOKEN not in response.text


@pytest.mark.integration
def test_runs_are_capped_per_demo_user_per_day(
    seeded_db: str, analytics_dsn: str, app_dsn: str, admin_dsn: str
) -> None:
    import psycopg

    with psycopg.connect(admin_dsn) as conn:  # start the day's count from zero for this user
        conn.execute("DELETE FROM demo_run_requests WHERE user_id = 'user-a-viewer'")
    client = _client(analytics_dsn, app_dsn, cap=2, user="user-a-viewer")

    codes = [client.post("/v1/runs", json=BODY, headers=_auth()).status_code for _ in range(3)]

    assert codes[:2] == [201, 201]
    assert codes[2] == 429
    last = client.post("/v1/runs", json=BODY, headers=_auth())
    assert last.json()["code"] == "QUOTA_EXCEEDED"


@pytest.mark.parametrize(
    "body",
    [
        {"task_text": "x", "script": "../../etc/passwd"},
        {"task_text": "x", "script": "no-such-script"},
        {"task_text": "", "script": "run-sample-q3-declines"},
        {"task_text": "x", "script": "run-sample-q3-declines", "tenant_id": "demo-b"},
    ],
)
def test_malformed_run_requests_are_rejected(body: dict[str, str]) -> None:
    response = _client(None, None).post("/v1/runs", json=body, headers=_auth())

    assert response.status_code in {404, 422}


def test_run_ids_are_server_generated() -> None:
    from agentops_api.runs import new_run_id

    first, second = new_run_id(), new_run_id()
    assert first != second
    assert first.startswith("api-") and uuid.UUID(first.removeprefix("api-"))
