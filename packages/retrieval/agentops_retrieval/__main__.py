"""Index chunks with DATABASE_URL, or benchmark read-only retrieval with ANALYTICS_DATABASE_URL.

Run it after every ``python -m agentops_data seed``: seeding replaces chunks and their embeddings.
"""

import argparse
import os
import sys
from pathlib import Path

import psycopg

from agentops_data.access import UnknownPrincipalError
from agentops_retrieval.benchmark import DEFAULT_DATASET, load_dataset, run_benchmark
from agentops_retrieval.embedding import HashingEmbedder
from agentops_retrieval.indexing import index_chunks


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m agentops_retrieval")
    parser.add_argument("command", choices=["index", "benchmark"])
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--git-sha", default=os.environ.get("GITHUB_SHA"))
    args = parser.parse_args(argv)

    if args.command == "benchmark":
        if args.out is None or args.git_sha is None:
            parser.error("benchmark requires --out and --git-sha (or GITHUB_SHA)")
        url = os.environ.get("ANALYTICS_DATABASE_URL")
        if not url:
            print("ANALYTICS_DATABASE_URL is not set", file=sys.stderr)
            return 2
        try:
            with psycopg.connect(url) as conn:
                report = run_benchmark(
                    conn, HashingEmbedder(), load_dataset(args.dataset), git_sha=args.git_sha
                )
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_bytes((report.model_dump_json(indent=2) + "\n").encode("utf-8"))
        except psycopg.Error as exc:
            print(f"database error {type(exc).__name__}", file=sys.stderr)
            return 2
        except (ValueError, OSError, UnknownPrincipalError) as exc:
            print(f"benchmark error: {exc}", file=sys.stderr)
            return 2
        aggregate = report.aggregate
        print(
            f"{report.dataset_version}: Recall@k={aggregate.mean_recall_at_k}, "
            f"MRR={aggregate.mrr}; forbidden hits={aggregate.forbidden_hits}"
        )
        return int(aggregate.forbidden_hits > 0)

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
