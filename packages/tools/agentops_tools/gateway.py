"""Server-side tool gateway (FR-005, FR-006, NFR-001, NFR-002).

Every tool call, approval request and approval decision passes through here, and every
outcome is written to ``policy_events``. The caller's tenant, user and run come from a
trusted ``CallContext`` built by the backend, never from tool arguments.

A write needs an approval bound to the principal, the run, the tool, the policy version and
the SHA-256 hash of the exact arguments; it expires, and it is consumed in the same
transaction that writes the sandbox ticket, so one approval writes at most one ticket.
"""

import hashlib
import json
import re
import uuid
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import psycopg
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ValidationError

from agentops_core.policy import POLICY_VERSION
from agentops_data.access import UnknownPrincipalError, principal_role, role_permissions
from agentops_retrieval.embedding import Embedder
from agentops_tools.read_tools import (
    TOOL_ARGUMENT_MODELS,
    IssueNotFoundError,
    TicketArgs,
    ToolContext,
    ToolOutput,
    get_issue_details,
    get_sales_summary,
    search_approved_documents,
)
from agentops_tools.tickets import (
    SandboxTicketService,
    TicketOutcomeUnknownError,
    TicketRejectedError,
)

REQUIRED_PERMISSION: dict[str, str] = {
    "get_sales_summary": "sales:read",
    "search_approved_documents": "docs:read",
    "get_issue_details": "issues:read",
    "create_followup_ticket": "tickets:write",
}
WRITE_TOOLS = frozenset({"create_followup_ticket"})
_RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")

_READS: dict[str, Callable[[ToolContext, Any], ToolOutput]] = {
    "get_sales_summary": get_sales_summary,
    "search_approved_documents": search_approved_documents,
    "get_issue_details": get_issue_details,
}


@dataclass(frozen=True)
class CallContext:
    """Who is calling and for which run; built by the trusted backend, never by the model."""

    tenant_id: str
    user_id: str
    run_id: str


@dataclass(frozen=True)
class ApprovalRequest:
    approval_id: str
    action_hash: str
    expires_at: datetime
    policy_version: str


@dataclass(frozen=True)
class RecoveryResult:
    execution_id: str
    run_id: str
    outcome: str


class GatewayDenied(Exception):  # noqa: N818 - a decision, not a fault
    def __init__(self, reason_code: str, detail: str = "") -> None:
        super().__init__(f"{reason_code}: {detail}" if detail else reason_code)
        self.reason_code = reason_code


def action_hash(ctx: CallContext, tool_name: str, args: BaseModel, policy_version: str) -> str:
    """SHA-256 of the canonical JSON of everything an approval vouches for."""
    canonical = json.dumps(
        {
            "tool": tool_name,
            "tenant_id": ctx.tenant_id,
            "principal_id": ctx.user_id,
            "run_id": ctx.run_id,
            "policy_version": policy_version,
            "arguments": args.model_dump(mode="json"),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def ticket_reference(approval_id: str) -> str:
    """Deterministic sandbox reference: the same approval always names the same ticket."""
    return "SBX-" + uuid.UUID(approval_id).hex[:12].upper()


class ToolGateway:
    def __init__(
        self,
        *,
        connect: Callable[[], psycopg.Connection],
        embedder: Embedder,
        policy_version: str = POLICY_VERSION,
        approval_ttl: timedelta = timedelta(minutes=15),
        tickets: SandboxTicketService | None = None,
    ) -> None:
        self._connect = connect
        self._embedder = embedder
        self.policy_version = policy_version
        self._approval_ttl = approval_ttl
        self._tickets = tickets if tickets is not None else SandboxTicketService(connect)

    # -- public API -------------------------------------------------------------------------
    def invoke(
        self,
        ctx: CallContext,
        tool_name: str,
        arguments: Mapping[str, object],
        approval_id: str | None = None,
    ) -> dict[str, Any]:
        with self._session() as conn:
            try:
                args = self._authorize(conn, ctx, tool_name, arguments)
                if tool_name in WRITE_TOOLS:
                    return self._write_ticket(conn, ctx, tool_name, args, approval_id)
                result = self._run_read(conn, ctx, tool_name, args)
            except GatewayDenied as denied:
                self._log(conn, ctx, "tool_call", tool_name, "deny", denied.reason_code)
                raise
            self._log(conn, ctx, "tool_call", tool_name, "allow", "AUTHORIZED")
            return result

    def request_approval(
        self, ctx: CallContext, tool_name: str, arguments: Mapping[str, object]
    ) -> ApprovalRequest:
        with self._session() as conn:
            try:
                args = self._authorize(conn, ctx, tool_name, arguments)
                if tool_name not in WRITE_TOOLS:
                    raise GatewayDenied("APPROVAL_NOT_APPLICABLE", "only writes need approval")
                digest = action_hash(ctx, tool_name, args, self.policy_version)
                approval_id = uuid.uuid4()
                with self._scope(conn, ctx):
                    row = conn.execute(
                        "INSERT INTO approvals (id, tenant_id, run_id, principal_id, tool_name,"
                        " action_hash, policy_version, expires_at)"
                        " VALUES (%s, %s, %s, %s, %s, %s, %s, now() + %s) RETURNING expires_at",
                        (
                            approval_id,
                            ctx.tenant_id,
                            ctx.run_id,
                            ctx.user_id,
                            tool_name,
                            digest,
                            self.policy_version,
                            self._approval_ttl,
                        ),
                    ).fetchone()
                    self._insert_event(
                        conn,
                        ctx,
                        "approval_request",
                        tool_name,
                        "allow",
                        "APPROVAL_REQUESTED",
                        digest,
                        approval_id,
                    )
            except GatewayDenied as denied:
                self._log(conn, ctx, "approval_request", tool_name, "deny", denied.reason_code)
                raise
        if row is None:  # pragma: no cover - INSERT ... RETURNING always returns the row
            raise GatewayDenied("APPROVAL_NOT_CREATED")
        return ApprovalRequest(str(approval_id), digest, row[0], self.policy_version)

    def decide(self, ctx: CallContext, approval_id: str, approve: bool) -> str:
        """The requesting principal approves or rejects a pending action for its run."""
        tool_name = "unknown"
        with self._session() as conn:
            try:
                key = self._approval_key(approval_id)
                with self._scope(conn, ctx):
                    row = conn.execute(
                        "SELECT tool_name, principal_id, run_id, status, expires_at <= now(),"
                        " action_hash FROM approvals WHERE id = %s AND tenant_id = %s FOR UPDATE",
                        (key, ctx.tenant_id),
                    ).fetchone()
                    if row is None:
                        raise GatewayDenied("APPROVAL_NOT_FOUND")
                    tool_name, principal_id, run_id, status, expired, digest = row
                    if principal_id != ctx.user_id:
                        raise GatewayDenied("APPROVAL_PRINCIPAL_MISMATCH")
                    if run_id != ctx.run_id:
                        raise GatewayDenied("APPROVAL_RUN_MISMATCH")
                    if status != "pending":
                        raise GatewayDenied("APPROVAL_ALREADY_DECIDED")
                    if expired:
                        raise GatewayDenied("APPROVAL_EXPIRED")
                    new_status = "approved" if approve else "rejected"
                    conn.execute(
                        "UPDATE approvals SET status = %s, decided_by = %s, decided_at = now()"
                        " WHERE id = %s",
                        (new_status, ctx.user_id, key),
                    )
                    self._insert_event(
                        conn,
                        ctx,
                        "approval_decision",
                        tool_name,
                        "allow",
                        "APPROVED" if approve else "REJECTED",
                        digest,
                        key,
                    )
            except GatewayDenied as denied:
                self._log(conn, ctx, "approval_decision", tool_name, "deny", denied.reason_code)
                raise
        return new_status

    # -- checks -----------------------------------------------------------------------------
    def _authorize(
        self,
        conn: psycopg.Connection,
        ctx: CallContext,
        tool_name: str,
        arguments: Mapping[str, object],
    ) -> BaseModel:
        model = TOOL_ARGUMENT_MODELS.get(tool_name)
        if model is None or tool_name not in REQUIRED_PERMISSION:
            raise GatewayDenied("TOOL_NOT_ALLOWED")
        if not _RUN_ID.fullmatch(ctx.run_id):
            raise GatewayDenied("INVALID_REQUEST", "malformed run id")
        try:
            role = principal_role(conn, ctx.tenant_id, ctx.user_id)
        except UnknownPrincipalError:
            raise GatewayDenied("UNKNOWN_PRINCIPAL") from None
        except ValueError:
            raise GatewayDenied("INVALID_REQUEST", "malformed tenant or user") from None
        if REQUIRED_PERMISSION[tool_name] not in role_permissions(conn, role):
            raise GatewayDenied("PERMISSION_DENIED")
        try:
            return model.model_validate(dict(arguments))
        except ValidationError:
            raise GatewayDenied("INVALID_ARGUMENTS") from None

    @staticmethod
    def _approval_key(approval_id: str | None) -> uuid.UUID:
        if approval_id is None:
            raise GatewayDenied("APPROVAL_REQUIRED")
        try:
            return uuid.UUID(approval_id)
        except ValueError:
            raise GatewayDenied("APPROVAL_NOT_FOUND") from None

    # -- execution --------------------------------------------------------------------------
    def _run_read(
        self, conn: psycopg.Connection, ctx: CallContext, tool_name: str, args: BaseModel
    ) -> dict[str, Any]:
        tool_ctx = ToolContext(conn, self._embedder, ctx.tenant_id, ctx.user_id)
        try:
            output = _READS[tool_name](tool_ctx, args)
        except IssueNotFoundError:
            raise GatewayDenied("NOT_FOUND") from None
        return {
            "evidence": [item.model_dump(mode="json") for item in output.evidence],
            "analytics": output.analytics.model_dump(mode="json") if output.analytics else None,
            "issue": output.issue.model_dump(mode="json") if output.issue else None,
        }

    def _write_ticket(
        self,
        conn: psycopg.Connection,
        ctx: CallContext,
        tool_name: str,
        args: BaseModel,
        approval_id: str | None,
    ) -> dict[str, Any]:
        if not isinstance(args, TicketArgs):  # pragma: no cover - guaranteed by the registry
            raise GatewayDenied("INVALID_ARGUMENTS")
        key = self._approval_key(approval_id)
        with self._scope(conn, ctx):
            row = conn.execute(
                "SELECT principal_id, run_id, tool_name, status, expires_at <= now(),"
                " policy_version, action_hash FROM approvals"
                " WHERE id = %s AND tenant_id = %s FOR UPDATE",
                (key, ctx.tenant_id),
            ).fetchone()
            if row is None:
                raise GatewayDenied("APPROVAL_NOT_FOUND")
            principal_id, run_id, approved_tool, status, expired, version, approved_hash = row
            if principal_id != ctx.user_id:
                raise GatewayDenied("APPROVAL_PRINCIPAL_MISMATCH")
            if run_id != ctx.run_id:
                raise GatewayDenied("APPROVAL_RUN_MISMATCH")
            if approved_tool != tool_name:
                raise GatewayDenied("APPROVAL_ACTION_MISMATCH")
            if status == "consumed":
                raise GatewayDenied("APPROVAL_ALREADY_USED")
            if status != "approved":
                raise GatewayDenied("APPROVAL_NOT_APPROVED")
            if expired:
                raise GatewayDenied("APPROVAL_EXPIRED")
            if version != self.policy_version:
                raise GatewayDenied("APPROVAL_POLICY_CHANGED")
            digest = action_hash(ctx, tool_name, args, self.policy_version)
            if digest != approved_hash:
                raise GatewayDenied("APPROVAL_ACTION_MISMATCH")

            # Reserve the one execution this approval allows, and consume the approval, in the
            # same transaction. The idempotency key is server-derived: the model cannot set it.
            execution_id = uuid.uuid4()
            reserved = conn.execute(
                "INSERT INTO tool_executions (id, tenant_id, run_id, principal_id, tool_name,"
                " idempotency_key, action_hash, approval_id, status, external_reference,"
                " request_json)"
                " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'reserved', %s, %s)"
                " ON CONFLICT (tenant_id, tool_name, idempotency_key) DO NOTHING RETURNING id",
                (
                    execution_id,
                    ctx.tenant_id,
                    ctx.run_id,
                    ctx.user_id,
                    tool_name,
                    f"approval:{key}",
                    digest,
                    key,
                    ticket_reference(str(key)),
                    Jsonb(args.model_dump(mode="json")),
                ),
            ).fetchone()
            if reserved is None:
                raise GatewayDenied("APPROVAL_ALREADY_USED")
            conn.execute(
                "UPDATE approvals SET status = 'consumed', consumed_at = now()"
                " WHERE id = %s AND status = 'approved'",
                (key,),
            )
            self._insert_event(
                conn, ctx, "tool_call", tool_name, "allow", "APPROVAL_VERIFIED", digest, key
            )
        result = self._execute(conn, ctx.tenant_id, execution_id)
        return {**result, "approval_id": str(key)}

    def _execute(
        self, conn: psycopg.Connection, tenant_id: str, execution_id: uuid.UUID
    ) -> dict[str, Any]:
        """Claim a reserved or reconciled execution, call the ticket service, record the outcome.

        A crash between the service's commit and the final update leaves the row ``executing``;
        ``recover_executions`` resolves it by external reference.
        """
        with self._tenant(conn, tenant_id):
            claimed = conn.execute(
                "UPDATE tool_executions SET status = 'executing',"
                " attempt_count = attempt_count + 1, updated_at = now()"
                " WHERE id = %s AND status IN ('reserved', 'uncertain')"
                " RETURNING run_id, principal_id, approval_id, external_reference, request_json",
                (execution_id,),
            ).fetchone()
        if claimed is None:
            raise GatewayDenied("EXECUTION_IN_PROGRESS")
        run_id, principal_id, approval, reference, request = claimed
        try:
            result = self._tickets.create(
                tenant_id=tenant_id,
                reference=reference,
                approval_id=str(approval),
                run_id=run_id,
                created_by=principal_id,
                ticket=request,
            )
        except TicketOutcomeUnknownError:
            self._finish(conn, tenant_id, execution_id, "uncertain", error_code="OUTCOME_UNKNOWN")
            raise GatewayDenied(
                "EXECUTION_UNCERTAIN", "outcome unknown; reconcile before retrying"
            ) from None
        except TicketRejectedError as rejected:
            self._finish(conn, tenant_id, execution_id, "failed", error_code=rejected.code)
            raise GatewayDenied("EXECUTION_FAILED", rejected.code) from None
        self._finish(conn, tenant_id, execution_id, "succeeded", result=result)
        return result

    def _finish(
        self,
        conn: psycopg.Connection,
        tenant_id: str,
        execution_id: uuid.UUID,
        status: str,
        *,
        result: dict[str, Any] | None = None,
        error_code: str | None = None,
    ) -> None:
        with self._tenant(conn, tenant_id):
            conn.execute(
                "UPDATE tool_executions SET status = %s, result_json = %s, error_code = %s,"
                " updated_at = now() WHERE id = %s AND status = 'executing'",
                (status, Jsonb(result) if result is not None else None, error_code, execution_id),
            )

    def recover_executions(
        self, tenant_id: str, *, stale_after: timedelta = timedelta(minutes=5)
    ) -> list[RecoveryResult]:
        """Resolve ``uncertain`` executions and ``executing`` ones idle for ``stale_after``.

        Each is first looked up by its external reference: found means it already happened
        (``reconciled_found``); not found means it is safe to run again under the same
        reference (``reconciled_retried``). Run by an operator or a scheduled job, never by the
        model. This is at-most-once for this ticket service, not a universal exactly-once
        guarantee: it relies on the service being idempotent and queryable by reference.
        """
        results: list[RecoveryResult] = []
        with self._session() as conn:
            with self._tenant(conn, tenant_id):
                rows = conn.execute(
                    "SELECT id, run_id, external_reference FROM tool_executions"
                    " WHERE tenant_id = %s AND (status = 'uncertain'"
                    " OR (status = 'executing' AND updated_at <= now() - %s))"
                    " ORDER BY created_at",
                    (tenant_id, stale_after),
                ).fetchall()
            for execution_id, run_id, reference in rows:
                found = self._tickets.lookup(tenant_id=tenant_id, reference=reference)
                if found is not None:
                    with self._tenant(conn, tenant_id):
                        conn.execute(
                            "UPDATE tool_executions SET status = 'succeeded', result_json = %s,"
                            " error_code = NULL, updated_at = now()"
                            " WHERE id = %s AND status IN ('executing', 'uncertain')",
                            (Jsonb(found), execution_id),
                        )
                    results.append(RecoveryResult(str(execution_id), run_id, "reconciled_found"))
                    continue
                with self._tenant(conn, tenant_id):
                    conn.execute(
                        "UPDATE tool_executions SET status = 'uncertain', updated_at = now()"
                        " WHERE id = %s AND status = 'executing'",
                        (execution_id,),
                    )
                try:
                    self._execute(conn, tenant_id, execution_id)
                    outcome = "reconciled_retried"
                except GatewayDenied as denied:
                    outcome = f"retry_{denied.reason_code.lower()}"
                results.append(RecoveryResult(str(execution_id), run_id, outcome))
        return results

    # -- plumbing ---------------------------------------------------------------------------
    def _session(self) -> psycopg.Connection:
        conn = self._connect()
        conn.autocommit = True  # every unit of work below is an explicit transaction
        return conn

    @staticmethod
    @contextmanager
    def _tenant(conn: psycopg.Connection, tenant_id: str) -> Iterator[None]:
        """A transaction scoped to a tenant, for system work without a calling principal."""
        with conn.transaction():
            conn.execute("SELECT set_config('app.tenant_id', %s, true)", (tenant_id,))
            yield

    @staticmethod
    @contextmanager
    def _scope(conn: psycopg.Connection, ctx: CallContext) -> Iterator[None]:
        """A transaction with row-level security scoped to the caller's tenant; an exception
        inside it rolls everything back."""
        with conn.transaction():
            conn.execute("SELECT set_config('app.tenant_id', %s, true)", (ctx.tenant_id,))
            yield

    def _insert_event(
        self,
        conn: psycopg.Connection,
        ctx: CallContext,
        event_type: str,
        tool_name: str,
        decision: str,
        reason_code: str,
        digest: str | None = None,
        approval: uuid.UUID | None = None,
    ) -> None:
        conn.execute(
            "INSERT INTO policy_events (tenant_id, run_id, principal_id, event_type, tool_name,"
            " decision, reason_code, policy_version, action_hash, approval_id)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (
                ctx.tenant_id,
                ctx.run_id,
                ctx.user_id,
                event_type,
                tool_name,
                decision,
                reason_code,
                self.policy_version,
                digest,
                approval,
            ),
        )

    def _log(
        self,
        conn: psycopg.Connection,
        ctx: CallContext,
        event_type: str,
        tool_name: str,
        decision: str,
        reason_code: str,
    ) -> None:
        """Record a decision in its own committed transaction (denials included)."""
        with self._scope(conn, ctx):
            self._insert_event(conn, ctx, event_type, tool_name, decision, reason_code)
