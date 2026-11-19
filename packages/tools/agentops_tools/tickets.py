"""The sandbox ticket service, treated as an external system (feat-006, D-010).

It commits on its own, separately from the gateway's registry, so a crash or a lost response
between its commit and the gateway's acknowledgment is a real possibility. Like a well-behaved
upstream API it is idempotent on the caller's external reference, and it can be queried by
that reference for reconciliation.
"""

from collections.abc import Callable
from typing import Any

import psycopg


class TicketOutcomeUnknownError(Exception):
    """The request may or may not have been applied (timeout, connection lost)."""


class TicketRejectedError(Exception):
    """The service definitely did not create the ticket."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


_COLUMNS = (
    "id, tenant_id, approval_id, run_id, created_by, title, description, priority, product_id"
)


class SandboxTicketService:
    def __init__(self, connect: Callable[[], psycopg.Connection]) -> None:
        self._connect = connect

    def create(
        self,
        *,
        tenant_id: str,
        reference: str,
        approval_id: str,
        run_id: str,
        created_by: str,
        ticket: dict[str, Any],
    ) -> dict[str, Any]:
        """Create the ticket named ``reference``; a repeat with the same content is a no-op."""
        values = (
            reference,
            tenant_id,
            approval_id,
            run_id,
            created_by,
            ticket["title"],
            ticket["description"],
            ticket["priority"],
            ticket.get("product_id"),
        )
        with self._connect() as conn, conn.transaction():
            conn.execute("SELECT set_config('app.tenant_id', %s, true)", (tenant_id,))
            conn.execute(
                f"INSERT INTO sandbox_tickets ({_COLUMNS})"  # noqa: S608 - fixed column list
                " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (id) DO NOTHING",
                values,
            )
            stored = conn.execute(
                f"SELECT {_COLUMNS} FROM sandbox_tickets WHERE id = %s",  # noqa: S608
                (reference,),
            ).fetchone()
        if stored is None or tuple(str(v) if v is not None else None for v in stored) != tuple(
            str(v) if v is not None else None for v in values
        ):
            raise TicketRejectedError("REFERENCE_CONFLICT")
        return {"ticket_id": reference, "status": "created"}

    def lookup(self, *, tenant_id: str, reference: str) -> dict[str, Any] | None:
        """The ticket created under ``reference``, if any."""
        with self._connect() as conn, conn.transaction():
            conn.execute("SELECT set_config('app.tenant_id', %s, true)", (tenant_id,))
            row = conn.execute(
                "SELECT id FROM sandbox_tickets WHERE id = %s AND tenant_id = %s",
                (reference, tenant_id),
            ).fetchone()
        return {"ticket_id": str(row[0]), "status": "created"} if row else None
