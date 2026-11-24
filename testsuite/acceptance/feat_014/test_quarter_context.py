"""feat-014 (FR-002, FR-004, FR-012, NFR-006): hosted planning knows the available quarters.

A hosted model invented 2023-Q3..2024-Q3 for data that covers 2026 only, so every live run
abstained. The planning prompt now states the tenant's quarters, and the sales tool defaults
to the two most recent quarters when the model omits both.
"""

import asyncio
import json
from decimal import Decimal
from typing import Any, cast

import psycopg
import pytest
from pydantic import ValidationError

from agentops_agents import workflow
from agentops_agents.policy import authorize_tool_calls
from agentops_agents.state import AgentRunState, RunDetail, RunStatus, TaskRequest
from agentops_agents.tools import READ_TOOLS
from agentops_agents.workflow import (
    NO_QUARTERS_CONTEXT,
    PLAN_PROMPT,
    RunDependencies,
    prompt_version,
    run_task,
)
from agentops_core.llm import LLMGateway, ModelCapabilities, ModelRequest, ModelResponse, ToolCall
from agentops_llm.mock import MOCK_MODEL, MockLLMProvider, MockScript
from agentops_retrieval.embedding import HashingEmbedder
from agentops_tools.gateway import ToolGateway
from agentops_tools.read_tools import SalesSummaryArgs, ToolContext, get_sales_summary
from testsuite.acceptance.feat_004.harness import APP_DSN

TASK = (
    "Analyze quarterly sales, identify the largest declines, consult relevant company "
    "policies and prepare a cited executive summary."
)


# --- offline: no network, no database ----------------------------------------------------


def test_tenant_without_sales_gets_the_no_data_statement(monkeypatch: pytest.MonkeyPatch) -> None:
    asked: list[str] = []

    def no_sales(conn: object, tenant_id: str) -> dict[str, Decimal]:
        asked.append(tenant_id)
        return {}

    monkeypatch.setattr(workflow, "revenue_by_quarter", no_sales)
    run = workflow._Run(cast(RunDependencies, None), cast(psycopg.Connection, object()), 0.0)
    state = cast(AgentRunState, {"tenant_id": "demo-b"})
    assert asyncio.run(run._quarters_context(state)) == NO_QUARTERS_CONTEXT
    assert asked == ["demo-b"]  # the run's own tenant, never a model-supplied one


def test_quarter_context_lists_quarters_and_the_two_most_recent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    quarters = {q: Decimal(1) for q in ("2025-Q3", "2025-Q4", "2026-Q1")}
    monkeypatch.setattr(workflow, "revenue_by_quarter", lambda conn, tenant_id: quarters)
    run = workflow._Run(cast(RunDependencies, None), cast(psycopg.Connection, object()), 0.0)
    text = asyncio.run(run._quarters_context(cast(AgentRunState, {"tenant_id": "demo-a"})))
    assert "2025-Q3, 2025-Q4, 2026-Q1" in text
    assert "2025-Q4 to 2026-Q1" in text
    assert "Use only these quarters" in text


def test_quarters_are_given_together_or_not_at_all() -> None:
    assert SalesSummaryArgs().from_quarter is None
    assert SalesSummaryArgs(from_quarter="2026-Q1", to_quarter="2026-Q2").to_quarter == "2026-Q2"
    with pytest.raises(ValidationError):
        SalesSummaryArgs(from_quarter="2026-Q1")
    call = ToolCall(id="c1", name="get_sales_summary", arguments={"to_quarter": "2026-Q2"})
    allowed, decisions = authorize_tool_calls([call], READ_TOOLS)
    assert allowed == []
    assert [d.reason_code for d in decisions] == ["INVALID_ARGUMENTS"]


def test_tool_description_and_prompt_version_cover_the_default() -> None:
    assert "Omit both quarters" in READ_TOOLS["get_sales_summary"].description
    assert prompt_version("single") == prompt_version("single")
    assert prompt_version("single") != prompt_version("specialists")


# --- integration: real workflow and gateway on local PostgreSQL ------------------------


class RecordingProvider:
    """Scripted mock that keeps every request the workflow sent."""

    name = "mock"

    def __init__(self, run_id: str, turns: list[dict[str, Any]]) -> None:
        self.inner = MockLLMProvider(
            [MockScript.model_validate({"run_id": run_id, "turns": turns})]
        )
        self.requests: list[ModelRequest] = []

    def capabilities(self, model: str) -> ModelCapabilities:
        return self.inner.capabilities(model)

    async def generate(self, request: ModelRequest, model: str) -> ModelResponse:
        self.requests.append(request)
        return await self.inner.generate(request, model)


def _run(
    analytics_dsn: str, run_id: str, turns: list[dict[str, Any]], orchestration: str = "single"
) -> tuple[RunDetail, RecordingProvider]:
    provider = RecordingProvider(run_id, turns)
    deps = RunDependencies(
        gateway=LLMGateway(provider, MOCK_MODEL),
        llm_provider=provider.name,
        llm_model=MOCK_MODEL,
        connect=lambda: psycopg.connect(analytics_dsn),
        embedder=HashingEmbedder(),
        tool_gateway=ToolGateway(
            connect=lambda: psycopg.connect(APP_DSN), embedder=HashingEmbedder()
        ),
        orchestration=orchestration,  # type: ignore[arg-type]
    )
    request = TaskRequest(
        run_id=run_id, tenant_id="demo-a", user_id="user-a-analyst", task_text=TASK
    )
    return asyncio.run(run_task(request, deps)), provider


def _sales_call(arguments: dict[str, object]) -> dict[str, Any]:
    return {"tool_calls": [{"id": "c1", "name": "get_sales_summary", "arguments": arguments}]}


EMPTY_REPORT = {"text": json.dumps({"summary": "No supported findings.", "findings": []})}


@pytest.mark.integration
def test_planning_prompt_states_the_seeded_quarters(seeded_db: str, analytics_dsn: str) -> None:
    _, provider = _run(analytics_dsn, "feat014-prompt", [_sales_call({}), EMPTY_REPORT])
    system = provider.requests[0].messages[0].content
    assert system.startswith(PLAN_PROMPT)
    assert "2026-Q1, 2026-Q2, 2026-Q3, 2026-Q4" in system
    assert "2026-Q3 to 2026-Q4" in system


@pytest.mark.integration
def test_omitted_quarters_compare_the_two_most_recent(seeded_db: str, analytics_dsn: str) -> None:
    detail, _ = _run(analytics_dsn, "feat014-default", [_sales_call({}), EMPTY_REPORT])
    assert detail.analytics is not None
    assert (detail.analytics.from_quarter, detail.analytics.to_quarter) == ("2026-Q3", "2026-Q4")
    # The seed recovers in Q4: no declines, so the run abstains instead of inventing one.
    assert detail.analytics.declines == []
    assert detail.status is RunStatus.ABSTAINED


@pytest.mark.integration
def test_explicit_quarters_without_data_still_abstain(seeded_db: str, analytics_dsn: str) -> None:
    turns = [_sales_call({"from_quarter": "2023-Q3", "to_quarter": "2024-Q3"})]
    detail, provider = _run(analytics_dsn, "feat014-nodata", turns)
    assert detail.status is RunStatus.ABSTAINED
    assert detail.abstain_reason == "NO_SALES_DATA"
    assert len(provider.requests) == 1


@pytest.mark.integration
def test_specialist_analyst_prompt_states_quarters_but_research_does_not(
    seeded_db: str, analytics_dsn: str
) -> None:
    search = {
        "tool_calls": [
            {"id": "r1", "name": "search_approved_documents", "arguments": {"query": "returns"}}
        ]
    }
    _, provider = _run(
        analytics_dsn, "feat014-spec", [search, _sales_call({}), EMPTY_REPORT], "specialists"
    )
    prompts = [request.messages[0].content for request in provider.requests[:2]]
    with_quarters = [p for p in prompts if "2026-Q3 to 2026-Q4" in p]
    assert len(with_quarters) == 1
    assert "data analyst" in with_quarters[0]


@pytest.mark.integration
def test_sales_tool_default_is_tenant_scoped(seeded_db: str, analytics_dsn: str) -> None:
    with psycopg.connect(analytics_dsn) as conn:
        ctx = ToolContext(conn=conn, embedder=HashingEmbedder(), tenant_id="demo-b", user_id="u")
        output = get_sales_summary(ctx, SalesSummaryArgs())
    assert output.analytics is not None
    # demo-b's own totals (demo-a has 47,500.00 and 49,500.00 for these quarters).
    assert (output.analytics.total_from, output.analytics.total_to) == (
        Decimal("155000.00"),
        Decimal("156000.00"),
    )
