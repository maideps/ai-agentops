"""Run feedback: record and export (FR-014). Uses the gateway's app login."""

import uuid
from typing import Any, Literal

import psycopg

from agentops_data.access import principal_role

Rating = Literal["up", "down"]


def record_feedback(
    conn: psycopg.Connection,
    *,
    tenant_id: str,
    user_id: str,
    run_id: str,
    rating: Rating,
    comment: str | None = None,
    eval_case_id: str | None = None,
) -> str:
    """Store one feedback row for a known principal; returns its id."""
    principal_role(conn, tenant_id, user_id)  # UnknownPrincipalError for anyone else
    feedback_id = uuid.uuid4()
    with conn.transaction():
        conn.execute("SELECT set_config('app.tenant_id', %s, true)", (tenant_id,))
        conn.execute(
            "INSERT INTO run_feedback (id, tenant_id, run_id, user_id, rating, comment,"
            " eval_case_id) VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (feedback_id, tenant_id, run_id, user_id, rating, comment, eval_case_id),
        )
    return str(feedback_id)


def export_feedback(conn: psycopg.Connection, tenant_id: str) -> list[dict[str, Any]]:
    """All feedback of a tenant, oldest first, as plain records for review."""
    with conn.transaction():
        conn.execute("SELECT set_config('app.tenant_id', %s, true)", (tenant_id,))
        rows = conn.execute(
            "SELECT id, run_id, user_id, rating, comment, eval_case_id, created_at"
            " FROM run_feedback WHERE tenant_id = %s ORDER BY created_at, id",
            (tenant_id,),
        ).fetchall()
    return [
        {
            "id": str(row[0]),
            "run_id": row[1],
            "user_id": row[2],
            "rating": row[3],
            "comment": row[4],
            "eval_case_id": row[5],
            "created_at": row[6].isoformat(),
        }
        for row in rows
    ]
