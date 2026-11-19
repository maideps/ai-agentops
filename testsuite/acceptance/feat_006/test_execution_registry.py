"""feat-006 (FR-007, NFR-003): one approved action, one ticket, whatever fails in between.

The sandbox ticket service commits on its own (like an external system). Faults are injected
after or before that commit; recovery reconciles by the deterministic external reference.
"""

import threading
from datetime import timedelta

import psycopg
import pytest

from agentops_evals.faults import FaultyTickets, SimulatedCrashError
from agentops_tools.gateway import CallContext, GatewayDenied, ToolGateway
from testsuite.acceptance.feat_005.helpers import TICKET, context, gateway, tickets_for_run

pytestmark = pytest.mark.integration


def _approved(gw: ToolGateway, ctx: CallContext) -> str:
    request = gw.request_approval(ctx, "create_followup_ticket", TICKET)
    gw.decide(ctx, request.approval_id, approve=True)
    return request.approval_id


def _executions(admin_dsn: str, run_id: str) -> list[tuple[str, int]]:
    with psycopg.connect(admin_dsn) as conn:
        rows = conn.execute(
            "SELECT status, attempt_count FROM tool_executions WHERE run_id = %s", (run_id,)
        ).fetchall()
    return [(str(status), int(attempts)) for status, attempts in rows]


def test_concurrent_retries_create_exactly_one_ticket(
    seeded_db: str, app_dsn: str, admin_dsn: str
) -> None:
    ctx = context()
    approval_id = _approved(gateway(app_dsn), ctx)
    barrier = threading.Barrier(8)
    outcomes: list[str] = []
    lock = threading.Lock()

    def attempt() -> None:
        gw = gateway(app_dsn)  # one client per thread, like independent retries
        barrier.wait()
        try:
            gw.invoke(ctx, "create_followup_ticket", TICKET, approval_id=approval_id)
            outcome = "created"
        except GatewayDenied as denied:
            outcome = denied.reason_code
        with lock:
            outcomes.append(outcome)

    threads = [threading.Thread(target=attempt) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert outcomes.count("created") == 1
    assert set(outcomes) - {"created"} == {"APPROVAL_ALREADY_USED"}
    assert tickets_for_run(admin_dsn, ctx.run_id) == 1
    assert _executions(admin_dsn, ctx.run_id) == [("succeeded", 1)]


def test_crash_after_external_commit_recovers_into_one_operation(
    seeded_db: str, app_dsn: str, admin_dsn: str
) -> None:
    ctx = context()
    approval_id = _approved(gateway(app_dsn), ctx)
    crashing = ToolGateway(
        connect=lambda: psycopg.connect(app_dsn),
        embedder=gateway(app_dsn)._embedder,
        tickets=FaultyTickets(lambda: psycopg.connect(app_dsn), "crash_after_commit"),
    )

    with pytest.raises(SimulatedCrashError):
        crashing.invoke(ctx, "create_followup_ticket", TICKET, approval_id=approval_id)
    assert _executions(admin_dsn, ctx.run_id) == [("executing", 1)]
    assert tickets_for_run(admin_dsn, ctx.run_id) == 1

    restarted = gateway(app_dsn)  # a new process after the restart
    results = restarted.recover_executions("demo-a", stale_after=timedelta(0))

    assert [(r.run_id, r.outcome) for r in results if r.run_id == ctx.run_id] == [
        (ctx.run_id, "reconciled_found")
    ]
    assert _executions(admin_dsn, ctx.run_id) == [("succeeded", 1)]
    assert tickets_for_run(admin_dsn, ctx.run_id) == 1
    with pytest.raises(GatewayDenied) as raised:
        restarted.invoke(ctx, "create_followup_ticket", TICKET, approval_id=approval_id)
    assert raised.value.reason_code == "APPROVAL_ALREADY_USED"


@pytest.mark.parametrize(
    ("fault", "expected_outcome", "expected_attempts"),
    [
        ("timeout_after_commit", "reconciled_found", 1),
        ("timeout_before_commit", "reconciled_retried", 2),
    ],
)
def test_ambiguous_outcome_is_reconciled_before_any_retry(
    seeded_db: str,
    app_dsn: str,
    admin_dsn: str,
    fault: str,
    expected_outcome: str,
    expected_attempts: int,
) -> None:
    ctx = context()
    approval_id = _approved(gateway(app_dsn), ctx)
    flaky = ToolGateway(
        connect=lambda: psycopg.connect(app_dsn),
        embedder=gateway(app_dsn)._embedder,
        tickets=FaultyTickets(lambda: psycopg.connect(app_dsn), fault),
    )

    with pytest.raises(GatewayDenied) as raised:
        flaky.invoke(ctx, "create_followup_ticket", TICKET, approval_id=approval_id)
    assert raised.value.reason_code == "EXECUTION_UNCERTAIN"
    assert _executions(admin_dsn, ctx.run_id) == [("uncertain", 1)]

    results = gateway(app_dsn).recover_executions("demo-a", stale_after=timedelta(minutes=5))

    assert [r.outcome for r in results if r.run_id == ctx.run_id] == [expected_outcome]
    assert _executions(admin_dsn, ctx.run_id) == [("succeeded", expected_attempts)]
    assert tickets_for_run(admin_dsn, ctx.run_id) == 1


def test_recovery_leaves_fresh_in_flight_executions_alone(
    seeded_db: str, app_dsn: str, admin_dsn: str
) -> None:
    ctx = context()
    approval_id = _approved(gateway(app_dsn), ctx)
    crashing = ToolGateway(
        connect=lambda: psycopg.connect(app_dsn),
        embedder=gateway(app_dsn)._embedder,
        tickets=FaultyTickets(lambda: psycopg.connect(app_dsn), "crash_after_commit"),
    )
    with pytest.raises(SimulatedCrashError):
        crashing.invoke(ctx, "create_followup_ticket", TICKET, approval_id=approval_id)

    results = gateway(app_dsn).recover_executions("demo-a", stale_after=timedelta(hours=1))

    assert [r for r in results if r.run_id == ctx.run_id] == []
    assert _executions(admin_dsn, ctx.run_id) == [("executing", 1)]


def test_app_login_cannot_rewrite_the_registry_history(seeded_db: str, app_dsn: str) -> None:
    with psycopg.connect(app_dsn) as conn, conn.transaction():
        conn.execute("SELECT set_config('app.tenant_id', 'demo-a', true)")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute("DELETE FROM tool_executions")
