"""feat-002 (NFR-010): migrations and the deterministic seed are repeatable and citable."""

import hashlib

import psycopg
import pytest

from agentops_data.migrations import apply_migrations
from agentops_data.seed import seed_dataset
from testsuite.conftest import DATASET_DIR

pytestmark = pytest.mark.integration


def _fingerprint(conn: psycopg.Connection) -> list[tuple[object, ...]]:
    return conn.execute(
        """
        SELECT 'sale', tenant_id || ':' || product_id || ':' || region || ':' || quarter,
               revenue::text FROM business_sales
        UNION ALL SELECT 'doc', id, content_sha256 FROM documents
        UNION ALL SELECT 'chunk', id, text_sha256 FROM document_chunks
        ORDER BY 1, 2
        """
    ).fetchall()


def test_migrations_are_recorded_and_idempotent(seeded_db: str) -> None:
    with psycopg.connect(seeded_db) as conn:
        assert apply_migrations(conn) == []
        versions = [row[0] for row in conn.execute("SELECT version FROM schema_migrations")]
    assert versions and versions == sorted(versions)


def test_pgvector_extension_is_installed(seeded_db: str) -> None:
    with psycopg.connect(seeded_db) as conn:
        row = conn.execute(
            "SELECT extversion FROM pg_extension WHERE extname = 'vector'"
        ).fetchone()
    assert row is not None


def test_seed_is_deterministic(seeded_db: str) -> None:
    with psycopg.connect(seeded_db) as conn:
        before = _fingerprint(conn)
        summary = seed_dataset(conn, DATASET_DIR)
        after = _fingerprint(conn)

    assert before == after
    assert (summary.tenants, summary.users, summary.sales_rows, summary.documents) == (2, 4, 64, 6)
    assert summary.chunks > summary.documents


def test_documents_and_chunks_have_stable_citable_ids(seeded_db: str) -> None:
    source = (DATASET_DIR / "documents" / "demo-a" / "returns-policy.md").read_bytes()
    with psycopg.connect(seeded_db) as conn:
        document = conn.execute(
            "SELECT content_sha256, source_uri, version FROM documents WHERE id = %s",
            ("doc-a-returns-policy",),
        ).fetchone()
        chunk_ids = [
            row[0]
            for row in conn.execute(
                "SELECT id FROM document_chunks WHERE document_id = %s ORDER BY chunk_index",
                ("doc-a-returns-policy",),
            )
        ]

    assert document == (
        hashlib.sha256(source).hexdigest(),
        "synthetic://documents/demo-a/returns-policy.md",
        1,
    )
    assert chunk_ids == [f"doc-a-returns-policy#{index}" for index in range(3)]
