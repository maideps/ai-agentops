"""``uv run python -m agentops_data {migrate,seed}`` (owner DATABASE_URL) or
``export-feedback --tenant T`` (app login in APP_DATABASE_URL)."""

import argparse
import json
import os
import sys
from pathlib import Path

import psycopg

from agentops_data.feedback import export_feedback
from agentops_data.migrations import apply_migrations
from agentops_data.seed import seed_dataset

DEFAULT_DATASET = Path("datasets/synthetic")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m agentops_data")
    parser.add_argument("command", choices=["migrate", "seed", "export-feedback"])
    parser.add_argument("--tenant", help="tenant for export-feedback")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    args = parser.parse_args(argv)

    if args.command == "export-feedback":
        app_url = os.environ.get("APP_DATABASE_URL")
        if not app_url or not args.tenant:
            print("export-feedback needs APP_DATABASE_URL and --tenant", file=sys.stderr)
            return 2
        with psycopg.connect(app_url) as conn:
            for record in export_feedback(conn, args.tenant):
                print(json.dumps(record, sort_keys=True))
        return 0

    url = os.environ.get("DATABASE_URL")
    if not url:
        print("DATABASE_URL is not set", file=sys.stderr)
        return 2
    with psycopg.connect(url) as conn:
        if args.command == "migrate":
            applied = apply_migrations(conn)
            print(f"applied {len(applied)} migration(s): {', '.join(applied) or 'none pending'}")
        else:
            summary = seed_dataset(conn, args.dataset)
            print(
                f"seeded {summary.tenants} tenants, {summary.users} users, "
                f"{summary.sales_rows} sales rows, {summary.documents} documents, "
                f"{summary.chunks} chunks"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
