"""feat-007 (FR-014): thumbs-up/down feedback per run, persisted with its run and eval-case
reference, exportable for review; writes need the demo bearer token."""

import uuid
from typing import Any

import psycopg
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from agentops_api.app import create_app
from agentops_api.settings import Settings
from agentops_data.feedback import export_feedback

TOKEN = "CANARY-SECRET-0120"  # noqa: S105 - a canary, not a credential


def _client(app_dsn: str | None, token: str | None = TOKEN) -> TestClient:
    settings = Settings(
        app_database_url=SecretStr(app_dsn) if app_dsn else None,
        demo_api_token=SecretStr(token) if token else None,
        demo_tenant_id="demo-a",
        demo_user_id="user-a-analyst",
    )
    return TestClient(create_app(settings))


def _auth(token: str = TOKEN) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.integration
def test_feedback_is_persisted_and_exported(seeded_db: str, app_dsn: str) -> None:
    run_id = f"run-fb-{uuid.uuid4().hex[:8]}"
    client = _client(app_dsn)

    up = client.post(f"/v1/runs/{run_id}/feedback", json={"rating": "up"}, headers=_auth())
    down = client.post(
        f"/v1/runs/{run_id}/feedback",
        json={
            "rating": "down",
            "comment": "Missed the NA stove cause",
            "eval_case_id": "normal-01",
        },
        headers=_auth(),
    )

    assert up.status_code == 201 and down.status_code == 201
    assert up.json()["run_id"] == run_id
    with psycopg.connect(app_dsn) as conn:
        rows = [r for r in export_feedback(conn, "demo-a") if r["run_id"] == run_id]
    assert [(r["rating"], r["eval_case_id"], r["user_id"]) for r in rows] == [
        ("up", None, "user-a-analyst"),
        ("down", "normal-01", "user-a-analyst"),
    ]


@pytest.mark.parametrize(
    ("headers", "status", "code"),
    [
        ({}, 401, "UNAUTHENTICATED"),
        ({"Authorization": "Bearer wrong-token"}, 401, "UNAUTHENTICATED"),
        ({"Authorization": f"Basic {TOKEN}"}, 401, "UNAUTHENTICATED"),
    ],
)
def test_feedback_requires_the_demo_token(headers: dict[str, str], status: int, code: str) -> None:
    response = _client(None).post("/v1/runs/run-1/feedback", json={"rating": "up"}, headers=headers)

    assert response.status_code == status
    body = response.json()
    assert body["code"] == code and body["request_id"]
    assert TOKEN not in response.text


def test_feedback_is_refused_when_no_token_is_configured() -> None:
    response = _client(None, token=None).post(
        "/v1/runs/run-1/feedback", json={"rating": "up"}, headers=_auth()
    )

    assert response.status_code == 503
    assert response.json()["code"] == "AUTH_NOT_CONFIGURED"


@pytest.mark.parametrize(
    ("path", "payload"),
    [
        ("/v1/runs/run-1/feedback", {"rating": "meh"}),
        ("/v1/runs/run-1/feedback", {"rating": "up", "comment": "x" * 501}),
        ("/v1/runs/run-1/feedback", {"rating": "up", "tenant_id": "demo-b"}),
        ("/v1/runs/bad id!/feedback", {"rating": "up"}),
    ],
)
def test_malformed_feedback_is_rejected(path: str, payload: dict[str, Any]) -> None:
    response = _client(None).post(path, json=payload, headers=_auth())

    assert response.status_code in {404, 422}


def test_http_spans_carry_no_token(span_exporter: Any) -> None:
    span_exporter.clear()

    _client(None).post("/v1/runs/run-1/feedback", json={"rating": "meh"}, headers=_auth())

    spans = [s for s in span_exporter.get_finished_spans() if s.name == "http.request"]
    assert spans
    assert spans[0].attributes["http.route"] == "/v1/runs/{run_id}/feedback"
    assert all(TOKEN not in s.to_json() for s in span_exporter.get_finished_spans())
