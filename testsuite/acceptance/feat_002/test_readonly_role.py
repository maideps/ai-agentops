"""feat-002 (FR-004): the analytics login cannot change anything, whatever SQL it sends."""

import psycopg
import pytest
from psycopg import errors

pytestmark = pytest.mark.integration

WRITES = [
    "INSERT INTO business_sales"
    " (tenant_id, product_id, product_name, region, quarter, revenue, units)"
    " VALUES ('demo-a', 999, 'x', 'EMEA', '2026-Q1', 1, 1)",
    "UPDATE business_sales SET revenue = 0",
    "DELETE FROM documents",
    "TRUNCATE document_chunks",
    "DROP TABLE business_sales",
    "ALTER TABLE documents ADD COLUMN pwned text",
    "CREATE TABLE pwned (id int)",
    "INSERT INTO schema_migrations (version, checksum) VALUES ('9999', 'x')",
]


@pytest.mark.parametrize("statement", WRITES)
def test_writes_through_the_analytics_role_are_denied(
    seeded_db: str, analytics_dsn: str, statement: str
) -> None:
    with psycopg.connect(analytics_dsn) as conn, conn.transaction():
        conn.execute("SELECT set_config('app.tenant_id', 'demo-a', true)")
        with pytest.raises(errors.InsufficientPrivilege):
            conn.execute(statement)


def test_seeded_data_is_unchanged_after_write_attempts(seeded_db: str) -> None:
    with psycopg.connect(seeded_db) as conn:
        counts = conn.execute(
            "SELECT (SELECT count(*) FROM business_sales), (SELECT count(*) FROM documents)"
        ).fetchone()
    assert counts == (64, 7)
