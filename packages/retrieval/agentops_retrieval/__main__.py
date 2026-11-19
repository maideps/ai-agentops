"""``uv run python -m agentops_retrieval index``: embed chunks, using the owner DATABASE_URL.

Run it after every ``python -m agentops_data seed``: seeding replaces chunks and their embeddings.
"""

import argparse
import os
import sys

import psycopg

from agentops_retrieval.embedding import HashingEmbedder
from agentops_retrieval.indexing import index_chunks


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m agentops_retrieval")
    parser.add_argument("command", choices=["index"])
    parser.parse_args(argv)

    url = os.environ.get("DATABASE_URL")
    if not url:
        print("DATABASE_URL is not set", file=sys.stderr)
        return 2
    embedder = HashingEmbedder()
    with psycopg.connect(url) as conn:
        changed = index_chunks(conn, embedder)
    print(f"embedded {changed} chunk(s) with {embedder.model_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
