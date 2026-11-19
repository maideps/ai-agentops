"""Typed, tenant-scoped read functions (FR-003 data side, FR-004).

Every function validates its arguments, sets ``app.tenant_id`` for its own transaction (row-level
security filters by it) and also filters by tenant in SQL. Run them on a connection of the
read-only analytics role; there is no function that takes SQL text.
"""

import re
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from decimal import Decimal

import psycopg

_TENANT_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,31}$")
_QUARTER = re.compile(r"^[0-9]{4}-Q[1-4]$")
_IDENTIFIER = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")


class UnknownPrincipalError(LookupError):
    """The user does not exist in the tenant (including users of other tenants)."""


class DocumentNotAccessibleError(LookupError):
    """Missing and forbidden documents raise the same error, so existence does not leak."""

    def __init__(self, document_id: str) -> None:
        super().__init__(f"document {document_id!r} is not accessible")


@dataclass(frozen=True)
class SalesRecord:
    tenant_id: str
    product_id: int
    product_name: str
    region: str
    quarter: str
    revenue: Decimal
    units: int


@dataclass(frozen=True)
class DocumentRef:
    id: str
    title: str
    source_uri: str
    access_label: str
    content_sha256: str
    version: int


@dataclass(frozen=True)
class Chunk:
    id: str
    document_id: str
    chunk_index: int
    text: str
    text_sha256: str


def _require(pattern: re.Pattern[str], value: str, what: str) -> str:
    if not pattern.fullmatch(value):
        msg = f"invalid {what}: {value[:40]!r}"
        raise ValueError(msg)
    return value


@contextmanager
def _tenant_scope(conn: psycopg.Connection, tenant_id: str) -> Iterator[None]:
    _require(_TENANT_ID, tenant_id, "tenant id")
    with conn.transaction():
        conn.execute("SELECT set_config('app.tenant_id', %s, true)", (tenant_id,))
        yield


def quarterly_sales(conn: psycopg.Connection, tenant_id: str, quarter: str) -> list[SalesRecord]:
    _require(_QUARTER, quarter, "quarter")
    with _tenant_scope(conn, tenant_id):
        rows = conn.execute(
            "SELECT tenant_id, product_id, product_name, region, quarter, revenue, units"
            " FROM business_sales WHERE tenant_id = %s AND quarter = %s"
            " ORDER BY product_id, region",
            (tenant_id, quarter),
        ).fetchall()
    return [SalesRecord(*row) for row in rows]


def revenue_by_quarter(conn: psycopg.Connection, tenant_id: str) -> dict[str, Decimal]:
    with _tenant_scope(conn, tenant_id):
        rows = conn.execute(
            "SELECT quarter, sum(revenue) FROM business_sales WHERE tenant_id = %s"
            " GROUP BY quarter ORDER BY quarter",
            (tenant_id,),
        ).fetchall()
    return {quarter: total for quarter, total in rows}


def _allowed_labels(conn: psycopg.Connection, tenant_id: str, user_id: str) -> list[str]:
    _require(_IDENTIFIER, user_id, "user id")
    rows = conn.execute(
        "SELECT a.access_label FROM users u"
        " JOIN role_document_access a ON a.role_id = u.role_id"
        " WHERE u.id = %s AND u.tenant_id = %s",
        (user_id, tenant_id),
    ).fetchall()
    if not rows:
        exists = conn.execute(
            "SELECT 1 FROM users WHERE id = %s AND tenant_id = %s", (user_id, tenant_id)
        ).fetchone()
        if exists is None:
            msg = f"user {user_id!r} is not a member of tenant {tenant_id!r}"
            raise UnknownPrincipalError(msg)
    return [label for (label,) in rows]


def documents_for_user(conn: psycopg.Connection, tenant_id: str, user_id: str) -> list[DocumentRef]:
    """Documents of the tenant whose access label the user's role grants."""
    with _tenant_scope(conn, tenant_id):
        labels = _allowed_labels(conn, tenant_id, user_id)
        rows = conn.execute(
            "SELECT id, title, source_uri, access_label, content_sha256, version FROM documents"
            " WHERE tenant_id = %s AND access_label = ANY(%s) ORDER BY id",
            (tenant_id, labels),
        ).fetchall()
    return [DocumentRef(*row) for row in rows]


def document_chunks(
    conn: psycopg.Connection, tenant_id: str, user_id: str, document_id: str
) -> list[Chunk]:
    """Chunks of one document the user may read, in order."""
    _require(_IDENTIFIER, document_id, "document id")
    with _tenant_scope(conn, tenant_id):
        labels = _allowed_labels(conn, tenant_id, user_id)
        permitted = conn.execute(
            "SELECT 1 FROM documents WHERE id = %s AND tenant_id = %s AND access_label = ANY(%s)",
            (document_id, tenant_id, labels),
        ).fetchone()
        if permitted is None:
            raise DocumentNotAccessibleError(document_id)
        rows = conn.execute(
            "SELECT id, document_id, chunk_index, text, text_sha256 FROM document_chunks"
            " WHERE document_id = %s AND tenant_id = %s ORDER BY chunk_index",
            (document_id, tenant_id),
        ).fetchall()
    return [Chunk(*row) for row in rows]
