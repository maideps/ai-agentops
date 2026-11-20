"""feat-010 (NFR-001, FR-008): run checkpoints are tenant-isolated. A paused run's state is only
visible to, and resumable by, a checkpointer scoped to the run's tenant."""

import uuid

import psycopg
import pytest

from agentops_agents.checkpoints import postgres_checkpointer
from agentops_agents.state import RunDetail, RunStatus, TaskRequest
from agentops_agents.workflow import RunDependencies, resume_task, run_task, thread_id_for
from agentops_core.aio import run as run_async
from agentops_core.llm import LLMGateway
from agentops_llm.mock import MOCK_MODEL, MockLLMProvider, MockScript
from agentops_retrieval.embedding import HashingEmbedder
from agentops_tools.gateway import ToolGateway
from testsuite.acceptance.feat_004.harness import LLM_FIXTURES, SAMPLE_TASK

pytestmark = pytest.mark.integration


def _deps(analytics_dsn: str, app_dsn: str, run_id: str, saver: object) -> RunDependencies:
    script = MockScript.model_validate_json(
        (LLM_FIXTURES / "run-sample-q3-declines.json").read_text(encoding="utf-8")
    ).model_copy(update={"run_id": run_id})
    embedder = HashingEmbedder()
    return RunDependencies(
        gateway=LLMGateway(MockLLMProvider(scripts=[script]), MOCK_MODEL),
        llm_provider="mock",
        llm_model=MOCK_MODEL,
        connect=lambda: psycopg.connect(analytics_dsn),
        embedder=embedder,
        tool_gateway=ToolGateway(connect=lambda: psycopg.connect(app_dsn), embedder=embedder),
        checkpointer=saver,  # type: ignore[arg-type]
    )


def _pause(analytics_dsn: str, app_dsn: str) -> tuple[str, RunDetail]:
    run_id = f"run-iso-{uuid.uuid4().hex[:10]}"
    request = TaskRequest(
        run_id=run_id,
        tenant_id="demo-a",
        user_id="user-a-analyst",
        task_text=SAMPLE_TASK,
        propose_followup=True,
    )

    async def go() -> RunDetail:
        async with postgres_checkpointer(app_dsn, tenant_id="demo-a") as saver:
            return await run_task(request, _deps(analytics_dsn, app_dsn, run_id, saver))

    return run_id, run_async(go())


def _rows(app_dsn: str, tenant: str | None, thread: str) -> int:
    with psycopg.connect(app_dsn) as conn, conn.transaction():
        if tenant is not None:
            conn.execute("SELECT set_config('app.tenant_id', %s, true)", (tenant,))
        row = conn.execute(
            "SELECT (SELECT count(*) FROM checkpoints WHERE thread_id = %s)"
            " + (SELECT count(*) FROM checkpoint_blobs WHERE thread_id = %s)"
            " + (SELECT count(*) FROM checkpoint_writes WHERE thread_id = %s)",
            (thread, thread, thread),
        ).fetchone()
    return int(row[0]) if row else 0


def test_thread_ids_carry_the_tenant(seeded_db: str, analytics_dsn: str, app_dsn: str) -> None:
    run_id, paused = _pause(analytics_dsn, app_dsn)

    assert paused.status is RunStatus.AWAITING_APPROVAL
    assert paused.thread_id == thread_id_for("demo-a", run_id) == f"demo-a/thread-{run_id}"


def test_checkpoint_rows_are_only_visible_to_their_tenant(
    seeded_db: str, analytics_dsn: str, app_dsn: str
) -> None:
    _, paused = _pause(analytics_dsn, app_dsn)

    assert _rows(app_dsn, "demo-a", paused.thread_id) > 0
    assert _rows(app_dsn, "demo-b", paused.thread_id) == 0
    assert _rows(app_dsn, None, paused.thread_id) == 0  # no tenant scope, no rows


def test_another_tenant_cannot_resume_the_run(
    seeded_db: str, analytics_dsn: str, app_dsn: str
) -> None:
    run_id, _ = _pause(analytics_dsn, app_dsn)

    async def intrude() -> RunDetail:
        async with postgres_checkpointer(app_dsn, tenant_id="demo-b") as saver:
            return await resume_task(
                run_id,
                _deps(analytics_dsn, app_dsn, run_id, saver),
                tenant_id="demo-a",
                approved=True,
            )

    with pytest.raises(LookupError):
        run_async(intrude())


def test_writing_into_another_tenants_thread_is_rejected(seeded_db: str, app_dsn: str) -> None:
    with psycopg.connect(app_dsn) as conn, conn.transaction():
        conn.execute("SELECT set_config('app.tenant_id', 'demo-b', true)")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute(
                "INSERT INTO checkpoints (thread_id, checkpoint_ns, checkpoint_id, checkpoint,"
                " metadata) VALUES ('demo-a/thread-forged', '', 'c1', '{}', '{}')"
            )


def test_a_checkpointer_needs_a_valid_tenant() -> None:
    with pytest.raises(ValueError, match="tenant"):
        postgres_checkpointer("postgresql://unused", tenant_id="demo-a; DROP TABLE x")
    with pytest.raises(ValueError, match="tenant"):
        thread_id_for("demo-a/../demo-b", "run-1")
