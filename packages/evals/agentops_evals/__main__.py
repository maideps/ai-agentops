"""Run the evaluation corpus in mock mode.

    ANALYTICS_DATABASE_URL=... APP_DATABASE_URL=... \\
        uv run python -m agentops_evals run --out evals-report.json
        uv run python -m agentops_evals benchmark   # single vs specialists, writes results

`run` exits 1 if any case fails. No hosted model is ever called.
"""

import argparse
import os
import sys
from pathlib import Path

from agentops_evals.benchmark import run_benchmark, write_benchmark
from agentops_evals.corpus import DEFAULT_CORPUS, load_corpus
from agentops_evals.runner import run_corpus


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m agentops_evals")
    parser.add_argument("command", choices=["run", "benchmark"])
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--out-dir", type=Path, default=Path("benchmarks/orchestration/v1"))
    args = parser.parse_args(argv)

    analytics, app = os.environ.get("ANALYTICS_DATABASE_URL"), os.environ.get("APP_DATABASE_URL")
    if not analytics or not app:
        print("ANALYTICS_DATABASE_URL and APP_DATABASE_URL must be set", file=sys.stderr)
        return 2
    if args.command == "benchmark":
        bench = run_benchmark(load_corpus(args.corpus), analytics_dsn=analytics, app_dsn=app)
        json_path, md_path = write_benchmark(bench, args.out_dir)
        print(f"{bench.recommendation}: {bench.rationale}")
        print(f"wrote {json_path} and {md_path}")
        return 0
    report = run_corpus(load_corpus(args.corpus), analytics_dsn=analytics, app_dsn=app)
    if args.out:
        args.out.write_bytes((report.model_dump_json(indent=2) + "\n").encode("utf-8"))
    print(
        f"{report.dataset_version} @ {report.git_sha[:7]} prompt {report.prompt_version}: "
        f"{report.passed}/{report.total} passed"
    )
    for result in report.results:
        if not result.passed:
            print(f"FAIL {result.case_id} trace={result.trace_id}: {'; '.join(result.failures)}")
    return 0 if report.failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
