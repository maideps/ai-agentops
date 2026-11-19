"""feat-002 (FR-003 data side, FR-004): typed, tenant-scoped reads through the analytics role."""

from decimal import Decimal

import psycopg
import pytest

from agentops_data.access import (
    DocumentNotAccessibleError,
    UnknownPrincipalError,
    document_chunks,
    documents_for_user,
    quarterly_sales,
    revenue_by_quarter,
)

pytestmark = pytest.mark.integration


@pytest.fixture
def analytics(seeded_db: str, analytics_dsn: str) -> psycopg.Connection:
    return psycopg.connect(analytics_dsn)


def test_revenue_totals_match_the_synthetic_dataset(analytics: psycopg.Connection) -> None:
    with analytics:
        demo_a = revenue_by_quarter(analytics, "demo-a")
        demo_b = revenue_by_quarter(analytics, "demo-b")

    assert demo_a == {
        "2026-Q1": Decimal("56000.00"),
        "2026-Q2": Decimal("56000.00"),
        "2026-Q3": Decimal("47500.00"),
        "2026-Q4": Decimal("49500.00"),
    }
    assert demo_b["2026-Q3"] == Decimal("155000.00")


def test_quarterly_sales_returns_only_the_requested_tenant(analytics: psycopg.Connection) -> None:
    with analytics:
        rows = quarterly_sales(analytics, "demo-a", "2026-Q3")

    assert len(rows) == 8
    assert {row.tenant_id for row in rows} == {"demo-a"}
    assert {row.product_id for row in rows} == {101, 102, 103, 104}


def test_without_a_tenant_scope_the_analytics_role_sees_nothing(
    analytics: psycopg.Connection,
) -> None:
    with analytics:
        counts = [
            analytics.execute(f"SELECT count(*) FROM {table}").fetchone()  # noqa: S608
            for table in ("business_sales", "documents", "document_chunks", "users")
        ]

    assert counts == [(0,), (0,), (0,), (0,)]


def test_a_tenant_scope_cannot_read_another_tenants_rows(analytics: psycopg.Connection) -> None:
    with analytics, analytics.transaction():
        analytics.execute("SELECT set_config('app.tenant_id', 'demo-a', true)")
        leaked = analytics.execute(
            "SELECT count(*) FROM business_sales WHERE tenant_id = 'demo-b'"
        ).fetchone()

    assert leaked == (0,)


@pytest.mark.parametrize(
    ("user_id", "expected"),
    [
        ("user-a-viewer", {"doc-a-press-kit"}),
        ("user-a-analyst", {"doc-a-press-kit", "doc-a-returns-policy", "doc-a-pricing-guidelines"}),
        (
            "user-a-admin",
            {
                "doc-a-press-kit",
                "doc-a-returns-policy",
                "doc-a-pricing-guidelines",
                "doc-a-board-notes",
            },
        ),
    ],
)
def test_documents_are_filtered_by_tenant_and_role(
    analytics: psycopg.Connection, user_id: str, expected: set[str]
) -> None:
    with analytics:
        documents = documents_for_user(analytics, "demo-a", user_id)

    assert {document.id for document in documents} == expected
    assert all(document.content_sha256 and document.source_uri for document in documents)


def test_a_user_of_another_tenant_is_unknown(analytics: psycopg.Connection) -> None:
    with analytics, pytest.raises(UnknownPrincipalError):
        documents_for_user(analytics, "demo-a", "user-b-analyst")


@pytest.mark.parametrize(
    "document_id",
    ["doc-b-supplier-policy", "doc-a-board-notes", "doc-does-not-exist"],
)
def test_forbidden_and_missing_documents_look_the_same(
    analytics: psycopg.Connection, document_id: str
) -> None:
    with analytics, pytest.raises(DocumentNotAccessibleError) as raised:
        document_chunks(analytics, "demo-a", "user-a-analyst", document_id)

    assert str(raised.value) == f"document {document_id!r} is not accessible"


def test_permitted_document_chunks_are_returned_in_order(analytics: psycopg.Connection) -> None:
    with analytics:
        chunks = document_chunks(analytics, "demo-a", "user-a-analyst", "doc-a-returns-policy")

    assert [chunk.id for chunk in chunks] == [f"doc-a-returns-policy#{index}" for index in range(3)]
    assert "30 days" in chunks[0].text


@pytest.mark.parametrize("tenant_id", ["", "DEMO-A", "demo-a' OR '1'='1", "x" * 40])
def test_malformed_tenant_ids_are_rejected_before_any_query(
    analytics: psycopg.Connection, tenant_id: str
) -> None:
    with analytics, pytest.raises(ValueError, match="tenant"):
        revenue_by_quarter(analytics, tenant_id)
