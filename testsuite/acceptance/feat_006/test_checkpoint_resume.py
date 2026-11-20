"""feat-006 (FR-008, NFR-003): a run that proposes a ticket pauses for approval, is checkpointed
in Postgres, and resumes in a fresh process with the same thread identity, without replaying
the model calls or tool calls it already made."""

import uuid
from collections.abc import Awaitable, Callable
from typing import Any

import psycopg
import pytest

from agentops_agents.checkpoints import postgres_checkpointer
from agentops_agents.state import RunDetail, RunStatus, TaskRequest
from agentops_agents.workflow import RunDependencies, resume_task, run_task
from agentops_core.aio import run as run_async
from agentops_core.llm import LLMGateway
from agentops_llm.mock import MOCK_MODEL, MockLLMProvider, MockScript
from agentops_retrieval.embedding import HashingEmbedder
from agentops_tools.gateway import CallContext
from testsuite.acceptance.feat_004.harness import LLM_FIXTURES, SAMPLE_TASK, CountingProvider
from testsuite.acceptance.feat_005.helpers import gateway, tickets_for_run

pytestmark = pytest.mark.integration


def _provider(run_id: str) -> CountingProvider:
    """The sample run's model script, registered under a fresh run id."""
    script = MockScript.model_validate_json(
        (LLM_FIXTURES / "run-sample-q3-declines.json").read_text(encoding="utf-8")
    ).model_copy(update={"run_id": run_id})
    return CountingProvider(MockLLMProvider(scripts=[script]))


def _in_process(
    admin_dsn: str,
    app_dsn: str,
    analytics_dsn: str,
    provider: CountingProvider,
    step: Callable[[RunDependencies], Awaitable[RunDetail]],
) -> RunDetail:
    """One 'process': its own checkpointer connection, graph and dependencies."""

    async def go() -> RunDetail:
        async with postgres_checkpointer(app_dsn, tenant_id="demo-a") as saver:
            deps = RunDependencies(
                gateway=LLMGateway(provider, MOCK_MODEL),
                llm_provider=provider.name,
                llm_model=MOCK_MODEL,
                connect=lambda: psycopg.connect(analytics_dsn),
                embedder=HashingEmbedder(),
                tool_gateway=gateway(app_dsn),
                checkpointer=saver,
            )
            return await step(deps)

    return run_async(go())


def _start(admin_dsn: str, app_dsn: str, analytics_dsn: str) -> tuple[str, RunDetail, int]:
    run_id = f"run-hitl-{uuid.uuid4().hex[:10]}"
    provider = _provider(run_id)
    request = TaskRequest(
        run_id=run_id,
        tenant_id="demo-a",
        user_id="user-a-analyst",
        task_text=SAMPLE_TASK,
        propose_followup=True,
    )
    detail = _in_process(
        admin_dsn, app_dsn, analytics_dsn, provider, lambda deps: run_task(request, deps)
    )
    return run_id, detail, provider.calls


def _resume(
    admin_dsn: str, app_dsn: str, analytics_dsn: str, run_id: str, approved: bool
) -> tuple[RunDetail, int]:
    provider = _provider(run_id)  # a restarted process: nothing in memory carries over

    async def step(deps: RunDependencies) -> RunDetail:
        return await resume_task(run_id, deps, tenant_id="demo-a", approved=approved)

    detail = _in_process(admin_dsn, app_dsn, analytics_dsn, provider, step)
    return detail, provider.calls


def _decide(app_dsn: str, run_id: str, approval_id: str, approve: bool) -> None:
    ctx = CallContext(tenant_id="demo-a", user_id="user-a-analyst", run_id=run_id)
    gateway(app_dsn).decide(ctx, approval_id, approve=approve)


def test_run_pauses_for_approval_with_a_bound_proposal(
    seeded_db: str, admin_dsn: str, app_dsn: str, analytics_dsn: str
) -> None:
    run_id, detail, calls = _start(admin_dsn, app_dsn, analytics_dsn)

    assert detail.status is RunStatus.AWAITING_APPROVAL
    assert detail.thread_id == f"demo-a/thread-{run_id}"
    assert detail.proposed_action is not None
    assert detail.proposed_action["tool"] == "create_followup_ticket"
    assert detail.proposed_action["arguments"]["product_id"] == 101
    assert len(detail.proposed_action["action_hash"]) == 64
    assert calls == 2
    assert tickets_for_run(admin_dsn, run_id) == 0


def test_approved_run_resumes_after_restart_and_writes_once(
    seeded_db: str, admin_dsn: str, app_dsn: str, analytics_dsn: str
) -> None:
    run_id, paused, _ = _start(admin_dsn, app_dsn, analytics_dsn)
    assert paused.proposed_action is not None
    _decide(app_dsn, run_id, paused.proposed_action["approval_id"], approve=True)

    resumed, calls_after_restart = _resume(admin_dsn, app_dsn, analytics_dsn, run_id, approved=True)

    assert resumed.status is RunStatus.COMPLETED
    assert resumed.thread_id == paused.thread_id
    assert resumed.action_result is not None
    assert str(resumed.action_result["ticket_id"]).startswith("SBX-")
    assert calls_after_restart == 0  # no model call replayed
    assert resumed.llm_calls == 2 and resumed.tool_calls_executed == 2
    assert resumed.report == paused.report
    assert tickets_for_run(admin_dsn, run_id) == 1


def test_resume_cannot_forge_an_approval(
    seeded_db: str, admin_dsn: str, app_dsn: str, analytics_dsn: str
) -> None:
    run_id, _, _ = _start(admin_dsn, app_dsn, analytics_dsn)

    # The caller says "approved", but nobody approved it in the gateway.
    resumed, _ = _resume(admin_dsn, app_dsn, analytics_dsn, run_id, approved=True)

    assert resumed.status is RunStatus.COMPLETED
    assert resumed.action_result is None
    assert [error.code for error in resumed.errors] == ["APPROVAL_NOT_APPROVED"]
    assert tickets_for_run(admin_dsn, run_id) == 0


def test_rejected_proposal_completes_without_a_write(
    seeded_db: str, admin_dsn: str, app_dsn: str, analytics_dsn: str
) -> None:
    run_id, paused, _ = _start(admin_dsn, app_dsn, analytics_dsn)
    assert paused.proposed_action is not None
    _decide(app_dsn, run_id, paused.proposed_action["approval_id"], approve=False)

    resumed, _ = _resume(admin_dsn, app_dsn, analytics_dsn, run_id, approved=False)

    assert resumed.status is RunStatus.COMPLETED
    assert resumed.action_result is None
    assert resumed.errors == []
    assert tickets_for_run(admin_dsn, run_id) == 0


def test_resuming_an_unknown_thread_is_refused(
    seeded_db: str, admin_dsn: str, app_dsn: str, analytics_dsn: str
) -> None:
    async def step(deps: RunDependencies) -> Any:
        return await resume_task("run-never-started", deps, tenant_id="demo-a", approved=True)

    with pytest.raises(LookupError):
        _in_process(admin_dsn, app_dsn, analytics_dsn, _provider("run-never-started"), step)
