"""Shared setup for feat-005: a gateway on the app login, unique run ids, ticket counting."""

import uuid

import psycopg

from agentops_retrieval.embedding import HashingEmbedder
from agentops_tools.gateway import CallContext, ToolGateway

TICKET = {
    "title": "Review EMEA receipt rule impact on trail shoe sales",
    "description": "Trail Running Shoes EMEA fell 4,000.00 from 2026-Q2 to 2026-Q3.",
    "priority": "high",
    "product_id": 101,
}


def gateway(app_dsn: str, **kwargs: object) -> ToolGateway:
    return ToolGateway(
        connect=lambda: psycopg.connect(app_dsn),
        embedder=HashingEmbedder(),
        **kwargs,  # type: ignore[arg-type]
    )


def context(
    user_id: str = "user-a-analyst", tenant_id: str = "demo-a", run_id: str | None = None
) -> CallContext:
    return CallContext(
        tenant_id=tenant_id, user_id=user_id, run_id=run_id or f"run-{uuid.uuid4().hex[:12]}"
    )


def tickets_for_run(admin_dsn: str, run_id: str) -> int:
    with psycopg.connect(admin_dsn) as conn:
        row = conn.execute(
            "SELECT count(*) FROM sandbox_tickets WHERE run_id = %s", (run_id,)
        ).fetchone()
    return int(row[0]) if row else 0


def events_for_run(admin_dsn: str, run_id: str) -> list[tuple[str, str, str, str]]:
    with psycopg.connect(admin_dsn) as conn:
        rows = conn.execute(
            "SELECT event_type, tool_name, decision, reason_code FROM policy_events"
            " WHERE run_id = %s ORDER BY id",
            (run_id,),
        ).fetchall()
    return [(str(a), str(b), str(c), str(d)) for a, b, c, d in rows]
