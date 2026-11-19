"""feat-004 (FR-002, FR-011, FR-012): abstention, rejection, budgets and time limits are explicit
terminal states, and no model call happens after a limit is hit."""

import itertools

import pytest

from agentops_agents.state import RunLimits, RunStatus
from testsuite.acceptance.feat_004.harness import run

pytestmark = pytest.mark.integration


def test_missing_data_abstains_without_a_synthesis_call(seeded_db: str, analytics_dsn: str) -> None:
    detail, provider = run(
        analytics_dsn,
        run_id="run-missing-data",
        task_text="Compare 2025-Q3 with 2025-Q4 sales and explain the largest declines.",
    )

    assert detail.status is RunStatus.ABSTAINED
    assert detail.abstain_reason == "NO_SALES_DATA"
    assert detail.report is None
    assert provider.calls == 1


def test_unknown_principal_is_rejected_before_any_model_call(
    seeded_db: str, analytics_dsn: str
) -> None:
    detail, provider = run(analytics_dsn, user_id="user-b-analyst")

    assert detail.status is RunStatus.REJECTED
    assert [error.code for error in detail.errors] == ["UNKNOWN_PRINCIPAL"]
    assert provider.calls == 0


def test_llm_call_budget_stops_before_the_second_call(seeded_db: str, analytics_dsn: str) -> None:
    detail, provider = run(analytics_dsn, limits=RunLimits(max_llm_calls=1))

    assert detail.status is RunStatus.BUDGET_EXHAUSTED
    assert [error.code for error in detail.errors] == ["MAX_LLM_CALLS"]
    assert provider.calls == 1
    assert detail.report is None


def test_tool_call_budget_is_terminal(seeded_db: str, analytics_dsn: str) -> None:
    detail, provider = run(analytics_dsn, limits=RunLimits(max_tool_calls=1))

    assert detail.status is RunStatus.BUDGET_EXHAUSTED
    assert [error.code for error in detail.errors] == ["MAX_TOOL_CALLS"]
    assert detail.tool_calls_executed == 0
    assert provider.calls == 1


def test_graph_step_limit_is_terminal(seeded_db: str, analytics_dsn: str) -> None:
    detail, provider = run(analytics_dsn, limits=RunLimits(max_graph_steps=3))

    assert detail.status is RunStatus.BUDGET_EXHAUSTED
    assert [error.code for error in detail.errors] == ["MAX_GRAPH_STEPS"]
    assert provider.calls <= 1


def test_deadline_is_terminal(seeded_db: str, analytics_dsn: str) -> None:
    ticks = itertools.count(start=0, step=60)  # every clock read advances one minute

    detail, provider = run(
        analytics_dsn, limits=RunLimits(max_run_seconds=90), clock=lambda: float(next(ticks))
    )

    assert detail.status is RunStatus.TIMED_OUT
    assert [error.code for error in detail.errors] == ["MAX_RUN_SECONDS"]
    assert provider.calls <= 1


def test_context_budget_drops_evidence_and_its_claims(seeded_db: str, analytics_dsn: str) -> None:
    detail, _ = run(analytics_dsn, limits=RunLimits(max_context_tokens=60))

    assert detail.context.dropped_evidence_ids
    assert detail.context.estimated_tokens <= 60
    assert detail.report is not None
    used = set(detail.context.included_evidence_ids)
    for finding in detail.report.findings:
        assert set(finding.citations) <= used
