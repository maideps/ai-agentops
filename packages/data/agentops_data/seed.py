"""Deterministic synthetic seed: same files in, same rows out (run as the schema owner)."""

import csv
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import psycopg
from psycopg import sql

SOURCE_SCHEME = "synthetic://"


@dataclass(frozen=True)
class SeedSummary:
    tenants: int
    users: int
    sales_rows: int
    documents: int
    chunks: int


def split_chunks(text: str) -> list[str]:
    """One chunk per paragraph (blank-line separated), whitespace-trimmed, empties dropped."""
    return [part.strip() for part in text.replace("\r\n", "\n").split("\n\n") if part.strip()]


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def seed_dataset(conn: psycopg.Connection, dataset_dir: Path) -> SeedSummary:
    """Replace all seeded rows with the contents of ``dataset_dir`` in one transaction."""
    directory: dict[str, Any] = json.loads((dataset_dir / "directory.json").read_text("utf-8"))
    with (dataset_dir / "sales.csv").open(newline="", encoding="utf-8") as handle:
        sales = list(csv.DictReader(handle))

    chunk_count = 0
    with conn.transaction():
        for table in (
            "document_chunks",
            "documents",
            "business_sales",
            "users",
            "role_document_access",
            "roles",
            "tenants",
        ):
            conn.execute(sql.SQL("DELETE FROM {}").format(sql.Identifier(table)))

        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO tenants (id, name) VALUES (%s, %s)",
                [(t["id"], t["name"]) for t in directory["tenants"]],
            )
            cur.executemany(
                "INSERT INTO roles (id, description) VALUES (%s, %s)",
                [(r["id"], r["description"]) for r in directory["roles"]],
            )
            cur.executemany(
                "INSERT INTO role_document_access (role_id, access_label) VALUES (%s, %s)",
                [(r["id"], label) for r in directory["roles"] for label in r["access_labels"]],
            )
            cur.executemany(
                "INSERT INTO users (id, tenant_id, display_name, role_id) VALUES (%s, %s, %s, %s)",
                [
                    (u["id"], u["tenant_id"], u["display_name"], u["role_id"])
                    for u in directory["users"]
                ],
            )
            cur.executemany(
                "INSERT INTO business_sales"
                " (tenant_id, product_id, product_name, region, quarter, revenue, units)"
                " VALUES (%s, %s, %s, %s, %s, %s, %s)",
                [
                    (
                        row["tenant_id"],
                        int(row["product_id"]),
                        row["product_name"],
                        row["region"],
                        row["quarter"],
                        row["revenue"],
                        int(row["units"]),
                    )
                    for row in sales
                ],
            )
            for document in directory["documents"]:
                raw = (dataset_dir / document["path"]).read_bytes()
                cur.execute(
                    "INSERT INTO documents"
                    " (id, tenant_id, title, source_uri, access_label, content_sha256)"
                    " VALUES (%s, %s, %s, %s, %s, %s)",
                    (
                        document["id"],
                        document["tenant_id"],
                        document["title"],
                        SOURCE_SCHEME + document["path"],
                        document["access_label"],
                        _sha256(raw),
                    ),
                )
                chunks = split_chunks(raw.decode("utf-8"))
                cur.executemany(
                    "INSERT INTO document_chunks"
                    " (id, document_id, tenant_id, chunk_index, text, text_sha256)"
                    " VALUES (%s, %s, %s, %s, %s, %s)",
                    [
                        (
                            f"{document['id']}#{index}",
                            document["id"],
                            document["tenant_id"],
                            index,
                            text,
                            _sha256(text.encode("utf-8")),
                        )
                        for index, text in enumerate(chunks)
                    ],
                )
                chunk_count += len(chunks)

    return SeedSummary(
        tenants=len(directory["tenants"]),
        users=len(directory["users"]),
        sales_rows=len(sales),
        documents=len(directory["documents"]),
        chunks=chunk_count,
    )
