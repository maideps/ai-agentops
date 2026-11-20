"""Postgres checkpointing for runs (FR-008, D-010), isolated per tenant (feat-010, D-014).

``setup_checkpoints`` creates LangGraph's checkpoint tables as the schema owner (the app login
has no CREATE privilege), grants the app login read/write on them, and enables row-level
security keyed on the tenant prefix of the thread id (``<tenant>/thread-<run_id>``).

``postgres_checkpointer`` opens an async saver whose connection is scoped to one tenant
(``app.tenant_id`` set when the connection opens), so it can only see and write that tenant's
threads. Use it with ``agentops_core.aio.run`` on Windows.
"""

import re
from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager

import psycopg
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg import sql
from psycopg.conninfo import make_conninfo

APP_GROUP_ROLE = "agentops_app_rw"
TENANT_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,31}$")
# Tables that hold per-thread state; checkpoint_migrations only records schema versions.
THREAD_TABLES = ("checkpoints", "checkpoint_blobs", "checkpoint_writes")


def require_tenant(tenant_id: str) -> str:
    if not TENANT_ID.fullmatch(tenant_id):
        msg = f"invalid tenant id: {tenant_id[:40]!r}"
        raise ValueError(msg)
    return tenant_id


def setup_checkpoints(owner_dsn: str) -> list[str]:
    """Create or upgrade the checkpoint tables, grant them, and isolate them; idempotent."""
    with PostgresSaver.from_conn_string(owner_dsn) as saver:
        saver.setup()
    with psycopg.connect(owner_dsn) as conn, conn.transaction():
        tables = [
            str(name)
            for (name,) in conn.execute(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
                " AND tablename LIKE 'checkpoint%' ORDER BY tablename"
            ).fetchall()
        ]
        for table in tables:
            conn.execute(
                sql.SQL("GRANT SELECT, INSERT, UPDATE, DELETE ON {} TO {}").format(
                    sql.Identifier(table), sql.Identifier(APP_GROUP_ROLE)
                )
            )
        for table in THREAD_TABLES:
            ident = sql.Identifier(table)
            conn.execute(sql.SQL("ALTER TABLE {} ENABLE ROW LEVEL SECURITY").format(ident))
            conn.execute(sql.SQL("DROP POLICY IF EXISTS tenant_isolation ON {}").format(ident))
            # FOR ALL: the same expression filters reads and checks writes.
            conn.execute(
                sql.SQL(
                    "CREATE POLICY tenant_isolation ON {} USING"
                    " (split_part(thread_id, '/', 1) = current_setting('app.tenant_id', true))"
                ).format(ident)
            )
    return tables


def postgres_checkpointer(
    dsn: str, *, tenant_id: str
) -> AbstractAsyncContextManager[AsyncPostgresSaver]:
    """An async saver whose connection can only see ``tenant_id``'s threads."""
    scoped = make_conninfo(dsn, options=f"-c app.tenant_id={require_tenant(tenant_id)}")

    @asynccontextmanager
    async def saver() -> AsyncIterator[AsyncPostgresSaver]:
        async with AsyncPostgresSaver.from_conn_string(scoped) as opened:
            yield opened

    return saver()
