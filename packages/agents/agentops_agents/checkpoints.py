"""Postgres checkpointing for runs (FR-008, D-010).

``setup_checkpoints`` creates LangGraph's checkpoint tables as the schema owner (the app login
has no CREATE privilege) and grants the app login read/write on them. ``postgres_checkpointer``
opens an async saver for one process; use it with ``agentops_core.aio.run`` on Windows.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import psycopg
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg import sql

APP_GROUP_ROLE = "agentops_app_rw"


def setup_checkpoints(owner_dsn: str) -> list[str]:
    """Create or upgrade the checkpoint tables and grant them to the app role; idempotent."""
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
    return tables


@asynccontextmanager
async def postgres_checkpointer(dsn: str) -> AsyncIterator[AsyncPostgresSaver]:
    async with AsyncPostgresSaver.from_conn_string(dsn) as saver:
        yield saver
