"""Forward-only SQL migrations, applied in file-name order, each in its own transaction."""

import hashlib
from dataclasses import dataclass
from importlib import resources

import psycopg

_LEDGER = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version    text        PRIMARY KEY,
    checksum   char(64)    NOT NULL,
    applied_at timestamptz NOT NULL DEFAULT now()
)
"""


@dataclass(frozen=True)
class Migration:
    version: str
    sql: str

    @property
    def checksum(self) -> str:
        return hashlib.sha256(self.sql.encode("utf-8")).hexdigest()


class MigrationDriftError(RuntimeError):
    """An applied migration file was edited after it ran."""


def available_migrations() -> list[Migration]:
    files = resources.files(__name__)
    return sorted(
        (
            Migration(version=item.name.removesuffix(".sql"), sql=item.read_text(encoding="utf-8"))
            for item in files.iterdir()
            if item.name.endswith(".sql")
        ),
        key=lambda migration: migration.version,
    )


def apply_migrations(conn: psycopg.Connection) -> list[str]:
    """Apply pending migrations; return the versions applied by this call."""
    with conn.transaction():
        conn.execute(_LEDGER)
        applied: dict[str, str] = dict(
            conn.execute("SELECT version, checksum FROM schema_migrations").fetchall()
        )

    newly_applied: list[str] = []
    for migration in available_migrations():
        recorded = applied.get(migration.version)
        if recorded is not None:
            if recorded.strip() != migration.checksum:
                msg = f"migration {migration.version} changed after it was applied"
                raise MigrationDriftError(msg)
            continue
        with conn.transaction():
            # Trusted, packaged SQL; bytes run as one multi-statement script (no parameters).
            conn.execute(migration.sql.encode("utf-8"))
            conn.execute(
                "INSERT INTO schema_migrations (version, checksum) VALUES (%s, %s)",
                (migration.version, migration.checksum),
            )
        newly_applied.append(migration.version)
    return newly_applied
