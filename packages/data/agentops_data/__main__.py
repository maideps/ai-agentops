"""``uv run python -m agentops_data {migrate,seed}`` using the owner connection in DATABASE_URL."""

import argparse
import os
import sys
from pathlib import Path

import psycopg

from agentops_data.migrations import apply_migrations
from agentops_data.seed import seed_dataset

DEFAULT_DATASET = Path("datasets/synthetic")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m agentops_data")
    parser.add_argument("command", choices=["migrate", "seed"])
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    args = parser.parse_args(argv)

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
