"""feat-011 (FR-001, FR-006, FR-013): approve or reject a proposed action and resume the run over
HTTP; read a run's current detail. Identity is the Phase 1 demo token."""

from typing import Any

import psycopg
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from agentops_api.app import create_app
from agentops_api.settings import Settings

pytestmark = pytest.mark.integration

TOKEN = "CANARY-SECRET-0140"  # noqa: S105 - a canary, not a credential
AUTH = {"Authorization": f"Bearer {TOKEN}"}
PROPOSE = {
    "task_text": "Analyze the largest Q3 declines and propose a follow-up ticket.",
    "script": "run-sample-q3-declines",
    "propose_followup": True,
}


@pytest.fixture
def client_for(analytics_dsn: str, app_dsn: str) -> Any:
    def make(user: str = "user-a-analyst", tenant: str = "demo-a") -> TestClient:
        settings = Settings(
            app_database_url=SecretStr(app_dsn),
            analytics_database_url=SecretStr(analytics_dsn),
            demo_api_token=SecretStr(TOKEN),
            demo_tenant_id=tenant,
            demo_user_id=user,
            max_requests_per_demo_user=10_000,
        )
        return TestClient(create_app(settings))

    return make


def _tickets(admin_dsn: str, run_id: str) -> int:
    with psycopg.connect(admin_dsn) as conn:
        row = conn.execute(
            "SELECT count(*) FROM sandbox_tickets WHERE run_id = %s", (run_id,)
        ).fetchone()
    return int(row[0]) if row else 0


def _paused(client: TestClient) -> dict[str, Any]:
    response = client.post("/v1/runs", json=PROPOSE, headers=AUTH)
    assert response.status_code == 201, response.text
    detail: dict[str, Any] = response.json()
    assert detail["status"] == "awaiting_approval"
    assert detail["proposed_action"]["tool"] == "create_followup_ticket"
    return detail


def _decide(client: TestClient, detail: dict[str, Any], decision: str) -> Any:
    approval = detail["proposed_action"]["approval_id"]
    return client.post(
        f"/v1/runs/{detail['run_id']}/approvals/{approval}",
        json={"decision": decision},
        headers=AUTH,
    )


def test_approve_resumes_the_run_and_writes_one_ticket(
    seeded_db: str, admin_dsn: str, client_for: Any
) -> None:
    client = client_for()
    paused = _paused(client)

    response = _decide(client, paused, "approve")

    assert response.status_code == 200, response.text
    done = response.json()
    assert done["status"] == "completed"
    assert done["thread_id"] == paused["thread_id"]
    assert done["action_result"]["ticket_id"].startswith("SBX-")
    assert done["llm_calls"] == paused["llm_calls"]  # resuming made no model call
    assert _tickets(admin_dsn, paused["run_id"]) == 1


def test_reject_completes_without_a_ticket(seeded_db: str, admin_dsn: str, client_for: Any) -> None:
    client = client_for()
    paused = _paused(client)

    response = _decide(client, paused, "reject")

    assert response.status_code == 200
    assert response.json()["status"] == "completed"
    assert response.json()["action_result"] is None
    assert _tickets(admin_dsn, paused["run_id"]) == 0


def test_a_second_decision_is_a_conflict_and_writes_nothing(
    seeded_db: str, admin_dsn: str, client_for: Any
) -> None:
    client = client_for()
    paused = _paused(client)
    assert _decide(client, paused, "approve").status_code == 200

    again = _decide(client, paused, "approve")

    assert again.status_code == 409
    assert again.json()["code"] == "APPROVAL_ALREADY_DECIDED"
    assert _tickets(admin_dsn, paused["run_id"]) == 1


def test_another_user_cannot_decide(seeded_db: str, admin_dsn: str, client_for: Any) -> None:
    paused = _paused(client_for())

    response = _decide(client_for(user="user-a-admin"), paused, "approve")

    assert response.status_code == 403
    assert response.json()["code"] == "APPROVAL_PRINCIPAL_MISMATCH"
    assert _tickets(admin_dsn, paused["run_id"]) == 0


def test_another_tenant_finds_nothing(seeded_db: str, admin_dsn: str, client_for: Any) -> None:
    paused = _paused(client_for())
    intruder = client_for(user="user-b-analyst", tenant="demo-b")

    read = intruder.get(f"/v1/runs/{paused['run_id']}", headers=AUTH)
    decide = _decide(intruder, paused, "approve")

    assert (read.status_code, decide.status_code) == (404, 404)
    assert _tickets(admin_dsn, paused["run_id"]) == 0


def test_get_shows_the_run_before_and_after_the_decision(seeded_db: str, client_for: Any) -> None:
    client = client_for()
    paused = _paused(client)

    before = client.get(f"/v1/runs/{paused['run_id']}", headers=AUTH)
    _decide(client, paused, "approve")
    after = client.get(f"/v1/runs/{paused['run_id']}", headers=AUTH)

    assert before.status_code == after.status_code == 200
    assert before.json()["status"] == "awaiting_approval"
    assert after.json()["status"] == "completed"
    assert after.json()["action_result"]["ticket_id"].startswith("SBX-")


@pytest.mark.parametrize(
    ("path", "body"),
    [
        ("/v1/runs/run-1/approvals/not-a-uuid", {"decision": "approve"}),
        ("/v1/runs/run-1/approvals/00000000-0000-0000-0000-000000000000", {"decision": "maybe"}),
        ("/v1/runs/bad id/approvals/00000000-0000-0000-0000-000000000000", {"decision": "approve"}),
    ],
)
def test_malformed_approval_requests_are_rejected(
    client_for: Any, path: str, body: dict[str, str]
) -> None:
    assert client_for().post(path, json=body, headers=AUTH).status_code in {404, 422}


def test_unknown_run_is_not_found(seeded_db: str, client_for: Any) -> None:
    response = client_for().get("/v1/runs/run-does-not-exist", headers=AUTH)

    assert response.status_code == 404
    assert response.json()["code"] == "RUN_NOT_FOUND"
