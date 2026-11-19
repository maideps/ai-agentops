"""feat-008 (FR-016): Research, Data Analyst and Reporting roles as subgraphs, an experiment
next to the single-workflow baseline (which stays the default)."""

import json
import time
from typing import Any

import psycopg
import pytest

from agentops_agents.state import RunDetail, RunStatus, TaskRequest
from agentops_agents.workflow import RunDependencies, run_task
from agentops_core.aio import run as run_async
from agentops_core.llm import LLMGateway
from agentops_evals.benchmark import specialist_turns
from agentops_llm.mock import MOCK_MODEL, MockLLMProvider, MockScript
from agentops_retrieval.embedding import HashingEmbedder
from agentops_tools.gateway import ToolGateway
from testsuite.acceptance.feat_004.harness import (
    APP_DSN,
    FIXED_TRACE_ID,
    LLM_FIXTURES,
    SAMPLE_TASK,
    CountingProvider,
    run,
)

pytestmark = pytest.mark.integration


def _specialists(
    analytics_dsn: str, run_id: str, turns: list[dict[str, Any]]
) -> tuple[RunDetail, int]:
    provider = CountingProvider(
        MockLLMProvider(scripts=[MockScript.model_validate({"run_id": run_id, "turns": turns})])
    )
    deps = RunDependencies(
        gateway=LLMGateway(provider, MOCK_MODEL),
        llm_provider=provider.name,
        llm_model=MOCK_MODEL,
        connect=lambda: psycopg.connect(analytics_dsn),
        embedder=HashingEmbedder(),
        tool_gateway=ToolGateway(
            connect=lambda: psycopg.connect(APP_DSN), embedder=HashingEmbedder()
        ),
        new_trace_id=lambda: FIXED_TRACE_ID,
        orchestration="specialists",
    )
    request = TaskRequest(
        run_id=run_id, tenant_id="demo-a", user_id="user-a-analyst", task_text=SAMPLE_TASK
    )
    return run_async(run_task(request, deps)), provider.calls


def test_specialists_reach_the_baseline_outcome_with_one_more_model_call(
    seeded_db: str, analytics_dsn: str
) -> None:
    baseline, baseline_provider = run(analytics_dsn)
    baseline_calls = baseline_provider.calls
    sample = json.loads((LLM_FIXTURES / "run-sample-q3-declines.json").read_text(encoding="utf-8"))
    specialists, specialist_calls = _specialists(
        analytics_dsn, f"run-spec-{time.time_ns()}", specialist_turns(sample["turns"])
    )

    assert specialists.status is baseline.status is RunStatus.COMPLETED
    assert specialists.analytics == baseline.analytics
    assert specialists.report == baseline.report
    denials = {
        (d.subject, d.reason_code) for d in specialists.policy_decisions if d.decision == "deny"
    }
    assert denials == {
        (d.subject, d.reason_code) for d in baseline.policy_decisions if d.decision == "deny"
    }
    assert (baseline_calls, specialist_calls) == (2, 3)
    assert specialists.tool_calls_executed == baseline.tool_calls_executed == 2


def test_each_role_only_gets_its_own_tool(seeded_db: str, analytics_dsn: str) -> None:
    swapped = [
        {
            "tool_calls": [
                {
                    "id": "r-1",
                    "name": "get_sales_summary",
                    "arguments": {"from_quarter": "2026-Q2", "to_quarter": "2026-Q3"},
                }
            ]
        },
        {
            "tool_calls": [
                {
                    "id": "a-1",
                    "name": "search_approved_documents",
                    "arguments": {"query": "returns", "k": 2},
                }
            ]
        },
    ]

    detail, calls = _specialists(analytics_dsn, f"run-spec-{time.time_ns()}", swapped)

    denied = {(d.subject, d.reason_code) for d in detail.policy_decisions if d.decision == "deny"}
    assert denied == {
        ("tool_call:r-1:get_sales_summary", "TOOL_NOT_ALLOWED"),
        ("tool_call:a-1:search_approved_documents", "TOOL_NOT_ALLOWED"),
    }
    assert detail.status is RunStatus.ABSTAINED
    assert detail.abstain_reason == "NO_EVIDENCE"
    assert calls == 2


def test_the_single_workflow_stays_the_default() -> None:
    assert RunDependencies.__dataclass_fields__["orchestration"].default == "single"
