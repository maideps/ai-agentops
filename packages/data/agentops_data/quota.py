"""Daily run quota for the demo user (feat-009). Uses the gateway's app login."""

import psycopg

from agentops_data.access import principal_role


class QuotaExceededError(Exception):
    """The user already made the allowed number of runs today (UTC)."""


def claim_run(
    conn: psycopg.Connection, *, tenant_id: str, user_id: str, run_id: str, cap: int
) -> int:
    """Record one run for today if the user is under ``cap``; return how many remain.

    An advisory lock per user serializes concurrent claims, so the cap holds under races.
    """
    principal_role(conn, tenant_id, user_id)  # UnknownPrincipalError for anyone else
    with conn.transaction():
        conn.execute("SELECT set_config('app.tenant_id', %s, true)", (tenant_id,))
        conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (f"{tenant_id}/{user_id}",))
        row = conn.execute(
            "SELECT count(*) FROM demo_run_requests WHERE tenant_id = %s AND user_id = %s"
            " AND created_at >= date_trunc('day', now() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC'",
            (tenant_id, user_id),
        ).fetchone()
        used = int(row[0]) if row else 0
        if used >= cap:
            raise QuotaExceededError
        conn.execute(
            "INSERT INTO demo_run_requests (tenant_id, user_id, run_id) VALUES (%s, %s, %s)",
            (tenant_id, user_id, run_id),
        )
    return cap - used - 1
