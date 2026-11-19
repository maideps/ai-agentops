"""Fault injection for reliability evaluation: a ticket service that fails on purpose."""

from collections.abc import Callable
from typing import Any

import psycopg

from agentops_tools.tickets import SandboxTicketService, TicketOutcomeUnknownError


class SimulatedCrashError(BaseException):
    """Stands in for the process dying: not an Exception, so nothing in the gateway catches it."""


class FaultyTickets(SandboxTicketService):
    """``crash_after_commit``, ``timeout_after_commit`` or ``timeout_before_commit``."""

    def __init__(self, connect: Callable[[], psycopg.Connection], fault: str) -> None:
        super().__init__(connect)
        self.fault = fault

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
        if self.fault == "timeout_before_commit":
            raise TicketOutcomeUnknownError("timed out before the service answered")
        result = super().create(
            tenant_id=tenant_id,
            reference=reference,
            approval_id=approval_id,
            run_id=run_id,
            created_by=created_by,
            ticket=ticket,
        )
        if self.fault == "crash_after_commit":
            raise SimulatedCrashError
        if self.fault == "timeout_after_commit":
            raise TicketOutcomeUnknownError("connection lost after the request was sent")
        return result
