"""The HTTP workflow selects the hosted adapter and stops before exceeding its reservation."""

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from agentops_api.app import create_app
from agentops_api.settings import Settings
from agentops_llm import hosted
from agentops_llm.hosted import GEMINI_FLASH_LITE, hosted_registry
from agentops_llm.litellm_provider import LiteLLMProvider
from agentops_llm.testing import stub_completion

CANARY = "CANARY-SECRET-0009"


@pytest.mark.integration
@pytest.mark.parametrize(
    "budget, status, calls", [(0.001, "budget_exhausted", 0), (0.7, "completed", 2)]
)
def test_hosted_http_run_uses_key_and_enforces_budget(
    seeded_db: str,
    analytics_dsn: str,
    app_dsn: str,
    monkeypatch: pytest.MonkeyPatch,
    budget: float,
    status: str,
    calls: int,
) -> None:
    made: list[LiteLLMProvider] = []
    invoked: list[dict[str, Any]] = []
    turns = json.loads(
        Path("fixtures/llm/run-sample-q3-declines.json").read_text(encoding="utf-8")
    )["turns"]
    stub = stub_completion(turns)

    async def completion(**kwargs: Any) -> Any:
        invoked.append(kwargs)
        return await stub(**kwargs)

    def factory(api_key: str | None, budget_usd: float) -> LiteLLMProvider:
        provider = LiteLLMProvider(
            registry=hosted_registry(),
            completion=completion,
            api_key=api_key,
            budget_usd=budget_usd,
        )
        made.append(provider)
        return provider

    monkeypatch.setattr(hosted, "hosted_provider", factory)
    settings = Settings(
        llm_mode="hosted_free",
        enable_live_llm=True,
        llm_model=GEMINI_FLASH_LITE,
        gemini_api_key=SecretStr(CANARY),
        llm_budget_usd=budget,
        analytics_database_url=SecretStr(analytics_dsn),
        app_database_url=SecretStr(app_dsn),
        demo_api_token=SecretStr(CANARY),
        demo_tenant_id="demo-a",
        demo_user_id="user-a-admin",
        max_requests_per_demo_user=1000,
    )
    client = TestClient(create_app(settings))
    response = client.post(
        "/v1/runs",
        json={"task_text": "Analyze the largest Q3 declines.", "script": "run-sample-q3-declines"},
        headers={"Authorization": f"Bearer {CANARY}"},
    )
    assert response.status_code == 201
    detail = response.json()
    assert detail["status"] == status
    assert detail["llm_model"] == GEMINI_FLASH_LITE
    assert len(invoked) == calls
    assert CANARY not in response.text
    assert all(call["api_key"] == CANARY and call["num_retries"] == 0 for call in invoked)
    assert made[0].reserved_usd(detail["run_id"]) <= budget
    if not calls:
        assert detail["errors"][0]["code"] == "BUDGET_EXCEEDED"
