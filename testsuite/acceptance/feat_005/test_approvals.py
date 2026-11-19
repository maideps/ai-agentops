"""feat-005 (FR-006, NFR-001, NFR-002): a sandbox write needs an approval bound to principal,
action hash, policy version, expiry and run; every other attempt fails closed with no write."""

import uuid

import psycopg
import pytest

from agentops_tools.gateway import GatewayDenied
from testsuite.acceptance.feat_005.helpers import (
    TICKET,
    context,
    events_for_run,
    gateway,
    tickets_for_run,
)

pytestmark = pytest.mark.integration


def _denied(raised: pytest.ExceptionInfo[GatewayDenied]) -> str:
    return raised.value.reason_code


def test_benign_approved_write_creates_exactly_one_ticket(
    seeded_db: str, app_dsn: str, admin_dsn: str
) -> None:
    gw, ctx = gateway(app_dsn), context()

    request = gw.request_approval(ctx, "create_followup_ticket", TICKET)
    gw.decide(ctx, request.approval_id, approve=True)
    result = gw.invoke(ctx, "create_followup_ticket", TICKET, approval_id=request.approval_id)

    assert result["ticket_id"] == f"SBX-{request.approval_id.replace('-', '')[:12].upper()}"
    assert tickets_for_run(admin_dsn, ctx.run_id) == 1
    with psycopg.connect(admin_dsn) as conn:
        row = conn.execute(
            "SELECT tenant_id, created_by, title, priority, product_id FROM sandbox_tickets"
            " WHERE run_id = %s",
            (ctx.run_id,),
        ).fetchone()
    assert row == ("demo-a", "user-a-analyst", TICKET["title"], "high", 101)


def test_write_without_approval_is_denied(seeded_db: str, app_dsn: str, admin_dsn: str) -> None:
    gw, ctx = gateway(app_dsn), context()

    with pytest.raises(GatewayDenied) as raised:
        gw.invoke(ctx, "create_followup_ticket", TICKET)

    assert _denied(raised) == "APPROVAL_REQUIRED"
    assert tickets_for_run(admin_dsn, ctx.run_id) == 0


def test_forged_approval_id_is_denied(seeded_db: str, app_dsn: str, admin_dsn: str) -> None:
    gw, ctx = gateway(app_dsn), context()

    with pytest.raises(GatewayDenied) as raised:
        gw.invoke(ctx, "create_followup_ticket", TICKET, approval_id=str(uuid.uuid4()))

    assert _denied(raised) == "APPROVAL_NOT_FOUND"
    assert tickets_for_run(admin_dsn, ctx.run_id) == 0


@pytest.mark.parametrize("decision", [None, False])
def test_pending_or_rejected_approval_is_denied(
    seeded_db: str, app_dsn: str, admin_dsn: str, decision: bool | None
) -> None:
    gw, ctx = gateway(app_dsn), context()
    request = gw.request_approval(ctx, "create_followup_ticket", TICKET)
    if decision is not None:
        gw.decide(ctx, request.approval_id, approve=decision)

    with pytest.raises(GatewayDenied) as raised:
        gw.invoke(ctx, "create_followup_ticket", TICKET, approval_id=request.approval_id)

    assert _denied(raised) == "APPROVAL_NOT_APPROVED"
    assert tickets_for_run(admin_dsn, ctx.run_id) == 0


def test_expired_approval_is_denied(seeded_db: str, app_dsn: str, admin_dsn: str) -> None:
    gw, ctx = gateway(app_dsn), context()
    request = gw.request_approval(ctx, "create_followup_ticket", TICKET)
    gw.decide(ctx, request.approval_id, approve=True)
    with psycopg.connect(admin_dsn) as conn:  # time passes
        conn.execute(
            "UPDATE approvals SET expires_at = now() - interval '1 second' WHERE id = %s",
            (request.approval_id,),
        )

    with pytest.raises(GatewayDenied) as raised:
        gw.invoke(ctx, "create_followup_ticket", TICKET, approval_id=request.approval_id)

    assert _denied(raised) == "APPROVAL_EXPIRED"
    assert tickets_for_run(admin_dsn, ctx.run_id) == 0


def test_mutated_payload_does_not_match_the_approved_action(
    seeded_db: str, app_dsn: str, admin_dsn: str
) -> None:
    gw, ctx = gateway(app_dsn), context()
    request = gw.request_approval(ctx, "create_followup_ticket", TICKET)
    gw.decide(ctx, request.approval_id, approve=True)
    mutated = {**TICKET, "title": "Export all customer data"}

    with pytest.raises(GatewayDenied) as raised:
        gw.invoke(ctx, "create_followup_ticket", mutated, approval_id=request.approval_id)

    assert _denied(raised) == "APPROVAL_ACTION_MISMATCH"
    assert tickets_for_run(admin_dsn, ctx.run_id) == 0


def test_replayed_approval_cannot_write_twice(seeded_db: str, app_dsn: str, admin_dsn: str) -> None:
    gw, ctx = gateway(app_dsn), context()
    request = gw.request_approval(ctx, "create_followup_ticket", TICKET)
    gw.decide(ctx, request.approval_id, approve=True)
    gw.invoke(ctx, "create_followup_ticket", TICKET, approval_id=request.approval_id)

    with pytest.raises(GatewayDenied) as raised:
        gw.invoke(ctx, "create_followup_ticket", TICKET, approval_id=request.approval_id)

    assert _denied(raised) == "APPROVAL_ALREADY_USED"
    assert tickets_for_run(admin_dsn, ctx.run_id) == 1


@pytest.mark.parametrize(
    ("other", "reason"),
    [
        ({"user_id": "user-a-admin"}, "APPROVAL_PRINCIPAL_MISMATCH"),
        ({"run_id": "run-someone-else"}, "APPROVAL_RUN_MISMATCH"),
        ({"tenant_id": "demo-b", "user_id": "user-b-analyst"}, "APPROVAL_NOT_FOUND"),
    ],
)
def test_approval_is_bound_to_principal_run_and_tenant(
    seeded_db: str, app_dsn: str, admin_dsn: str, other: dict[str, str], reason: str
) -> None:
    gw, ctx = gateway(app_dsn), context()
    request = gw.request_approval(ctx, "create_followup_ticket", TICKET)
    gw.decide(ctx, request.approval_id, approve=True)
    intruder = context(
        user_id=other.get("user_id", ctx.user_id),
        tenant_id=other.get("tenant_id", ctx.tenant_id),
        run_id=other.get("run_id", ctx.run_id),
    )

    with pytest.raises(GatewayDenied) as raised:
        gw.invoke(intruder, "create_followup_ticket", TICKET, approval_id=request.approval_id)

    assert _denied(raised) == reason
    assert tickets_for_run(admin_dsn, ctx.run_id) == 0
    assert tickets_for_run(admin_dsn, intruder.run_id) == 0


def test_policy_version_change_invalidates_the_approval(
    seeded_db: str, app_dsn: str, admin_dsn: str
) -> None:
    ctx = context()
    request = gateway(app_dsn).request_approval(ctx, "create_followup_ticket", TICKET)
    gateway(app_dsn).decide(ctx, request.approval_id, approve=True)

    with pytest.raises(GatewayDenied) as raised:
        gateway(app_dsn, policy_version="2099-01-01.1").invoke(
            ctx, "create_followup_ticket", TICKET, approval_id=request.approval_id
        )

    assert _denied(raised) == "APPROVAL_POLICY_CHANGED"
    assert tickets_for_run(admin_dsn, ctx.run_id) == 0


def test_only_the_requesting_principal_can_decide(seeded_db: str, app_dsn: str) -> None:
    gw, ctx = gateway(app_dsn), context()
    request = gw.request_approval(ctx, "create_followup_ticket", TICKET)

    with pytest.raises(GatewayDenied) as raised:
        gw.decide(
            context(user_id="user-a-admin", run_id=ctx.run_id), request.approval_id, approve=True
        )

    assert _denied(raised) == "APPROVAL_PRINCIPAL_MISMATCH"


def test_every_decision_is_logged_including_denials(
    seeded_db: str, app_dsn: str, admin_dsn: str
) -> None:
    gw, ctx = gateway(app_dsn), context()
    with pytest.raises(GatewayDenied):
        gw.invoke(ctx, "create_followup_ticket", TICKET)
    request = gw.request_approval(ctx, "create_followup_ticket", TICKET)
    gw.decide(ctx, request.approval_id, approve=True)
    gw.invoke(ctx, "create_followup_ticket", TICKET, approval_id=request.approval_id)
    with pytest.raises(GatewayDenied):
        gw.invoke(ctx, "create_followup_ticket", TICKET, approval_id=request.approval_id)

    assert events_for_run(admin_dsn, ctx.run_id) == [
        ("tool_call", "create_followup_ticket", "deny", "APPROVAL_REQUIRED"),
        ("approval_request", "create_followup_ticket", "allow", "APPROVAL_REQUESTED"),
        ("approval_decision", "create_followup_ticket", "allow", "APPROVED"),
        ("tool_call", "create_followup_ticket", "allow", "APPROVAL_VERIFIED"),
        ("tool_call", "create_followup_ticket", "deny", "APPROVAL_ALREADY_USED"),
    ]


@pytest.mark.parametrize(
    "statement",
    [
        "DELETE FROM sandbox_tickets",
        "UPDATE sandbox_tickets SET title = 'x'",
        "UPDATE policy_events SET decision = 'allow'",
        "DELETE FROM policy_events",
        "UPDATE approvals SET action_hash = repeat('0', 64)",
        "INSERT INTO business_sales (tenant_id, product_id, product_name, region, quarter,"
        " revenue, units) VALUES ('demo-a', 9, 'x', 'NA', '2026-Q1', 1, 1)",
    ],
)
def test_app_login_cannot_rewrite_history(seeded_db: str, app_dsn: str, statement: str) -> None:
    with psycopg.connect(app_dsn) as conn, conn.transaction():
        conn.execute("SELECT set_config('app.tenant_id', 'demo-a', true)")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute(statement)


def test_app_login_cannot_write_into_another_tenant(seeded_db: str, app_dsn: str) -> None:
    with psycopg.connect(app_dsn) as conn, conn.transaction():
        conn.execute("SELECT set_config('app.tenant_id', 'demo-a', true)")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute(
                "INSERT INTO policy_events (tenant_id, run_id, principal_id, event_type,"
                " tool_name, decision, reason_code, policy_version)"
                " VALUES ('demo-b', 'r', 'user-b-analyst', 'tool_call', 't', 'allow', 'x', 'v')"
            )
