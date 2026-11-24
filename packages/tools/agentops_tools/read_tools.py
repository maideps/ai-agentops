"""Typed tool arguments, results and the read-only tool implementations.

Tenant and user always come from the caller's trusted context (``ToolContext``), never from
arguments: every argument model forbids extra fields, so a smuggled ``tenant_id`` is invalid.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal, Self

import psycopg
from pydantic import BaseModel, ConfigDict, Field, model_validator

from agentops_data.access import SalesRecord, issue_by_id, quarterly_sales, revenue_by_quarter
from agentops_retrieval.embedding import Embedder
from agentops_retrieval.search import search_documents

QUARTER_PATTERN = r"^[0-9]{4}-Q[1-4]$"


class _Args(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SalesSummaryArgs(_Args):
    """Both quarters, or neither for the tenant's two most recent quarters with data."""

    from_quarter: str | None = Field(default=None, pattern=QUARTER_PATTERN)
    to_quarter: str | None = Field(default=None, pattern=QUARTER_PATTERN)
    top_n: int = Field(default=3, ge=1, le=10)

    @model_validator(mode="after")
    def _both_or_neither(self) -> Self:
        if (self.from_quarter is None) != (self.to_quarter is None):
            msg = "give both from_quarter and to_quarter, or neither"
            raise ValueError(msg)
        return self


class DocumentSearchArgs(_Args):
    query: str = Field(min_length=1, max_length=300)
    k: int = Field(default=4, ge=1, le=5)


class IssueDetailsArgs(_Args):
    issue_id: str = Field(pattern=r"^ISSUE-[A-Z]-[0-9]{1,6}$")


class TicketArgs(_Args):
    """The sandbox ticket payload. Its hash is what an approval binds to."""

    title: str = Field(min_length=5, max_length=120)
    description: str = Field(min_length=1, max_length=2000)
    priority: Literal["low", "medium", "high"] = "medium"
    product_id: int | None = Field(default=None, ge=1)


TOOL_ARGUMENT_MODELS: dict[str, type[BaseModel]] = {
    "get_sales_summary": SalesSummaryArgs,
    "search_approved_documents": DocumentSearchArgs,
    "get_issue_details": IssueDetailsArgs,
    "create_followup_ticket": TicketArgs,
}


class _Result(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class DeclineRow(_Result):
    product_id: int
    product_name: str
    region: str
    from_revenue: Decimal
    to_revenue: Decimal
    change: Decimal
    citations: list[str]


class SalesAnalytics(_Result):
    from_quarter: str
    to_quarter: str
    total_from: Decimal
    total_to: Decimal
    declines: list[DeclineRow]


class Evidence(_Result):
    id: str
    kind: Literal["sales", "document", "issue"]
    source_uri: str
    text: str


class IssueDetails(_Result):
    id: str
    title: str
    body: str
    state: str
    labels: list[str]


@dataclass(frozen=True)
class ToolContext:
    conn: psycopg.Connection
    embedder: Embedder
    tenant_id: str
    user_id: str


@dataclass(frozen=True)
class ToolOutput:
    evidence: list[Evidence]
    analytics: SalesAnalytics | None = None
    issue: IssueDetails | None = None


def sales_evidence_id(record: SalesRecord) -> str:
    return f"sales:{record.tenant_id}:{record.product_id}:{record.region}:{record.quarter}"


def _sales_evidence(record: SalesRecord) -> Evidence:
    return Evidence(
        id=sales_evidence_id(record),
        kind="sales",
        source_uri=(
            f"sales://{record.tenant_id}/{record.product_id}/{record.region}/{record.quarter}"
        ),
        text=(
            f"{record.product_name} {record.region} {record.quarter}: revenue {record.revenue}, "
            f"units {record.units}"
        ),
    )


def get_sales_summary(ctx: ToolContext, args: SalesSummaryArgs) -> ToolOutput:
    """Largest quarter-over-quarter revenue declines per product and region."""
    from_quarter, to_quarter = args.from_quarter, args.to_quarter
    if from_quarter is None or to_quarter is None:
        available = list(revenue_by_quarter(ctx.conn, ctx.tenant_id))
        if len(available) < 2:
            return ToolOutput(evidence=[], analytics=None)
        from_quarter, to_quarter = available[-2], available[-1]
    before = quarterly_sales(ctx.conn, ctx.tenant_id, from_quarter)
    after = quarterly_sales(ctx.conn, ctx.tenant_id, to_quarter)
    if not before or not after:
        return ToolOutput(evidence=[], analytics=None)

    previous = {(row.product_id, row.region): row for row in before}
    rows: list[tuple[SalesRecord, SalesRecord]] = [
        (previous[(row.product_id, row.region)], row)
        for row in after
        if (row.product_id, row.region) in previous
        and row.revenue < previous[(row.product_id, row.region)].revenue
    ]
    rows.sort(
        key=lambda pair: (pair[1].revenue - pair[0].revenue, pair[1].product_id, pair[1].region)
    )
    top = rows[: args.top_n]

    declines = [
        DeclineRow(
            product_id=new.product_id,
            product_name=new.product_name,
            region=new.region,
            from_revenue=old.revenue,
            to_revenue=new.revenue,
            change=new.revenue - old.revenue,
            citations=[sales_evidence_id(old), sales_evidence_id(new)],
        )
        for old, new in top
    ]
    analytics = SalesAnalytics(
        from_quarter=from_quarter,
        to_quarter=to_quarter,
        total_from=sum((row.revenue for row in before), Decimal("0")),
        total_to=sum((row.revenue for row in after), Decimal("0")),
        declines=declines,
    )
    evidence = [_sales_evidence(record) for pair in top for record in pair]
    return ToolOutput(evidence=evidence, analytics=analytics)


def search_approved_documents(ctx: ToolContext, args: DocumentSearchArgs) -> ToolOutput:
    """Document chunks the user may read, closest to the query first."""
    hits = search_documents(
        ctx.conn,
        ctx.embedder,
        tenant_id=ctx.tenant_id,
        user_id=ctx.user_id,
        query=args.query,
        k=args.k,
    )
    return ToolOutput(
        evidence=[
            Evidence(id=hit.id, kind="document", source_uri=hit.source_uri, text=hit.text)
            for hit in hits
        ]
    )


class IssueNotFoundError(LookupError):
    """Missing and other-tenant issues look the same."""


def get_issue_details(ctx: ToolContext, args: IssueDetailsArgs) -> ToolOutput:
    """One seeded issue of the caller's tenant (GitHub-issue fixture)."""
    issue = issue_by_id(ctx.conn, ctx.tenant_id, args.issue_id)
    if issue is None:
        msg = f"issue {args.issue_id!r} is not accessible"
        raise IssueNotFoundError(msg)
    details = IssueDetails(
        id=issue.id, title=issue.title, body=issue.body, state=issue.state, labels=issue.labels
    )
    evidence = Evidence(
        id=f"issue:{issue.id}",
        kind="issue",
        source_uri=f"issues://{ctx.tenant_id}/{issue.id}",
        text=f"{issue.title}. {issue.body}",
    )
    return ToolOutput(evidence=[evidence], issue=details)
