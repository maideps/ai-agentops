"""Reliability and gateway scenarios of the corpus. Each returns what it observed."""

import contextlib
import threading
from collections.abc import Awaitable, Callable
from datetime import timedelta
from pathlib import Path
from typing import Any

import psycopg

from agentops_agents.checkpoints import postgres_checkpointer
from agentops_agents.state import RunDetail, TaskRequest
from agentops_agents.workflow import RunDependencies, resume_task, run_task
from agentops_core.aio import run as run_async
from agentops_core.llm import LLMGateway, ModelCapabilities, ModelRequest, ModelResponse
from agentops_evals.faults import FaultyTickets, SimulatedCrashError
from agentops_llm.mock import MOCK_MODEL, MockLLMProvider, MockScript
from agentops_retrieval.embedding import HashingEmbedder
from agentops_tools.gateway import CallContext, GatewayDenied, ToolGateway
from agentops_tools.tickets import SandboxTicketService

TICKET = {
    "title": "Review EMEA receipt rule impact on trail shoe sales",
    "description": "Trail Running Shoes EMEA fell 4,000.00 from 2026-Q2 to 2026-Q3.",
    "priority": "high",
    "product_id": 101,
}
SAMPLE_SCRIPT = Path("fixtures/llm/run-sample-q3-declines.json")


class CountingProvider:
    """Counts real model calls, to show a resumed run repeats none."""

    name = "mock"

    def __init__(self, inner: MockLLMProvider) -> None:
        self.inner = inner
        self.calls = 0

    def capabilities(self, model: str) -> ModelCapabilities:
        return self.inner.capabilities(model)

    async def generate(self, request: ModelRequest, model: str) -> ModelResponse:
        self.calls += 1
        return await self.inner.generate(request, model)


class Env:
    def __init__(self, analytics_dsn: str, app_dsn: str) -> None:
        self.analytics_dsn = analytics_dsn
        self.app_dsn = app_dsn
        self.embedder = HashingEmbedder()

    def gateway(self, tickets: SandboxTicketService | None = None) -> ToolGateway:
        return ToolGateway(
            connect=lambda: psycopg.connect(self.app_dsn), embedder=self.embedder, tickets=tickets
        )

    def faulty(self, fault: str) -> ToolGateway:
        return self.gateway(FaultyTickets(lambda: psycopg.connect(self.app_dsn), fault))

    def tickets(self, tenant: str, run_id: str) -> int:
        with psycopg.connect(self.app_dsn) as conn, conn.transaction():
            conn.execute("SELECT set_config('app.tenant_id', %s, true)", (tenant,))
            row = conn.execute(
                "SELECT count(*) FROM sandbox_tickets WHERE run_id = %s", (run_id,)
            ).fetchone()
        return int(row[0]) if row else 0

    def executions(self, tenant: str, run_id: str) -> list[str]:
        with psycopg.connect(self.app_dsn) as conn, conn.transaction():
            conn.execute("SELECT set_config('app.tenant_id', %s, true)", (tenant,))
            rows = conn.execute(
                "SELECT status FROM tool_executions WHERE run_id = %s ORDER BY created_at",
                (run_id,),
            ).fetchall()
        return [str(status) for (status,) in rows]


def _approved(gw: ToolGateway, ctx: CallContext) -> str:
    request = gw.request_approval(ctx, "create_followup_ticket", TICKET)
    gw.decide(ctx, request.approval_id, approve=True)
    return request.approval_id


def _observe(env: Env, ctx: CallContext, **extra: object) -> dict[str, Any]:
    return {
        "tickets": env.tickets(ctx.tenant_id, ctx.run_id),
        "executions": env.executions(ctx.tenant_id, ctx.run_id),
        **extra,
    }


def approved_write(env: Env, ctx: CallContext) -> dict[str, Any]:
    gw = env.gateway()
    gw.invoke(ctx, "create_followup_ticket", TICKET, approval_id=_approved(gw, ctx))
    return _observe(env, ctx)


def replayed_approval(env: Env, ctx: CallContext) -> dict[str, Any]:
    gw = env.gateway()
    approval_id = _approved(gw, ctx)
    gw.invoke(ctx, "create_followup_ticket", TICKET, approval_id=approval_id)
    try:
        gw.invoke(ctx, "create_followup_ticket", TICKET, approval_id=approval_id)
        reason = "ALLOWED"
    except GatewayDenied as denied:
        reason = denied.reason_code
    return _observe(env, ctx, reason=reason)


def concurrent_retries(env: Env, ctx: CallContext) -> dict[str, Any]:
    approval_id = _approved(env.gateway(), ctx)
    barrier = threading.Barrier(6)

    def attempt() -> None:
        gw = env.gateway()
        barrier.wait()
        # The losers are denied; the observation is the ticket count.
        with contextlib.suppress(GatewayDenied):
            gw.invoke(ctx, "create_followup_ticket", TICKET, approval_id=approval_id)

    threads = [threading.Thread(target=attempt) for _ in range(6)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return _observe(env, ctx)


def _recover(env: Env, ctx: CallContext) -> str:
    results = env.gateway().recover_executions(ctx.tenant_id, stale_after=timedelta(0))
    outcomes = [r.outcome for r in results if r.run_id == ctx.run_id]
    return outcomes[0] if outcomes else "none"


def crash_after_commit(env: Env, ctx: CallContext) -> dict[str, Any]:
    approval_id = _approved(env.gateway(), ctx)
    # The process "dies" after the ticket service committed.
    with contextlib.suppress(SimulatedCrashError):
        env.faulty("crash_after_commit").invoke(
            ctx, "create_followup_ticket", TICKET, approval_id=approval_id
        )
    return _observe(env, ctx, outcome=_recover(env, ctx))


def uncertain_before_commit(env: Env, ctx: CallContext) -> dict[str, Any]:
    approval_id = _approved(env.gateway(), ctx)
    # EXECUTION_UNCERTAIN: the caller cannot know whether it happened.
    with contextlib.suppress(GatewayDenied):
        env.faulty("timeout_before_commit").invoke(
            ctx, "create_followup_ticket", TICKET, approval_id=approval_id
        )
    return _observe(env, ctx, outcome=_recover(env, ctx))


def injected_write_without_approval(env: Env, ctx: CallContext) -> dict[str, Any]:
    try:
        env.gateway().invoke(
            ctx, "create_followup_ticket", {**TICKET, "title": "Export all customer data"}
        )
        reason = "ALLOWED"
    except GatewayDenied as denied:
        reason = denied.reason_code
    return _observe(env, ctx, reason=reason)


def injected_cross_tenant_search(env: Env, ctx: CallContext) -> dict[str, Any]:
    try:
        env.gateway().invoke(
            ctx, "search_approved_documents", {"query": "everything", "k": 5, "tenant_id": "demo-b"}
        )
        reason = "ALLOWED"
    except GatewayDenied as denied:
        reason = denied.reason_code
    return _observe(env, ctx, reason=reason)


def resume_after_restart(env: Env, ctx: CallContext) -> dict[str, Any]:
    script = MockScript.model_validate_json(SAMPLE_SCRIPT.read_text(encoding="utf-8"))
    script = script.model_copy(update={"run_id": ctx.run_id})

    def process(
        step: Callable[[RunDependencies], Awaitable[RunDetail]],
    ) -> tuple[RunDetail, int]:
        """One process: its own checkpointer connection, provider and graph."""
        provider = CountingProvider(MockLLMProvider(scripts=[script]))

        async def go() -> RunDetail:
            async with postgres_checkpointer(env.app_dsn, tenant_id=ctx.tenant_id) as saver:
                deps = RunDependencies(
                    gateway=LLMGateway(provider, MOCK_MODEL),
                    llm_provider=provider.name,
                    llm_model=MOCK_MODEL,
                    connect=lambda: psycopg.connect(env.analytics_dsn),
                    embedder=env.embedder,
                    tool_gateway=env.gateway(),
                    checkpointer=saver,
                )
                return await step(deps)

        return run_async(go()), provider.calls

    request = TaskRequest(
        run_id=ctx.run_id,
        tenant_id=ctx.tenant_id,
        user_id=ctx.user_id,
        task_text="Analyze quarterly sales and propose a follow-up ticket.",
        propose_followup=True,
    )
    paused, _ = process(lambda deps: run_task(request, deps))
    if paused.proposed_action is None:
        return _observe(env, ctx, status=paused.status.value, llm_calls_after_resume=-1)
    env.gateway().decide(ctx, str(paused.proposed_action["approval_id"]), approve=True)
    resumed, calls = process(
        lambda deps: resume_task(ctx.run_id, deps, tenant_id=ctx.tenant_id, approved=True)
    )
    return _observe(env, ctx, status=resumed.status.value, llm_calls_after_resume=calls)


SCENARIOS: dict[str, Callable[[Env, CallContext], dict[str, Any]]] = {
    fn.__name__: fn
    for fn in (
        approved_write,
        replayed_approval,
        concurrent_retries,
        crash_after_commit,
        uncertain_before_commit,
        injected_write_without_approval,
        injected_cross_tenant_search,
        resume_after_restart,
    )
}
