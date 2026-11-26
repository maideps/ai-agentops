"""Run the evaluation corpus in mock mode, or explicitly opt into bounded live calls.

    ANALYTICS_DATABASE_URL=... APP_DATABASE_URL=... \\
        uv run python -m agentops_evals run --out evals-report.json
        uv run python -m agentops_evals benchmark   # single vs specialists, writes results

`run` exits 1 if any case fails. Live calls require --live, live environment opt-in, a
GEMINI_API_KEY and --budget-usd; the budget caps each run and the whole command.
"""

import argparse
import math
import os
import sys
from pathlib import Path

from agentops_core.llm import LLMError, LLMErrorCode
from agentops_evals.benchmark import run_benchmark, write_benchmark
from agentops_evals.corpus import DEFAULT_CORPUS, load_corpus
from agentops_evals.replays import record_replays
from agentops_evals.runner import run_corpus
from agentops_llm.hosted import hosted_provider
from agentops_llm.litellm_provider import LiteLLMProvider


def _live_provider(budget_usd: float, min_call_interval: float = 0.0) -> LiteLLMProvider:
    if (
        os.environ.get("LLM_MODE") not in ("hosted_free", "live_paid")
        or os.environ.get("ENABLE_LIVE_LLM", "").lower() != "true"
    ):
        raise LLMError(
            LLMErrorCode.PROVIDER_UNAVAILABLE,
            "--live requires a live LLM_MODE and ENABLE_LIVE_LLM=true",
        )
    return hosted_provider(
        os.environ.get("GEMINI_API_KEY"),
        budget_usd,
        total_budget_usd=budget_usd,
        min_call_interval=min_call_interval,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m agentops_evals")
    parser.add_argument("command", choices=["run", "benchmark", "record-replays"])
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--out-dir", type=Path)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--budget-usd", type=float)
    parser.add_argument(
        "--stop-after-rate-limited",
        type=int,
        default=3,
        help="live only: stop after this many consecutive rate-limited cases (0 = never)",
    )
    parser.add_argument(
        "--min-call-interval",
        type=float,
        default=0.0,
        help="live only: minimum seconds between model calls, to stay under provider rate limits",
    )
    args = parser.parse_args(argv)

    live_provider = None
    if args.live:
        if args.command == "record-replays":
            parser.error("record-replays is mock-only")
        if args.budget_usd is None or not math.isfinite(args.budget_usd) or args.budget_usd <= 0:
            parser.error("--live requires a finite positive --budget-usd")
        if args.command == "run" and args.out is None:
            parser.error("--live run requires --out to preserve failures and usage")
        if args.stop_after_rate_limited < 0:
            parser.error("--stop-after-rate-limited must be >= 0")
        if not math.isfinite(args.min_call_interval) or args.min_call_interval < 0:
            parser.error("--min-call-interval must be a finite number of seconds >= 0")
        try:
            live_provider = _live_provider(args.budget_usd, args.min_call_interval)
        except LLMError as exc:
            print(f"{exc.code.value}: {exc.message}", file=sys.stderr)
            return 2
    elif args.budget_usd is not None:
        parser.error("--budget-usd requires --live")
    elif args.min_call_interval:
        parser.error("--min-call-interval requires --live")

    analytics, app = os.environ.get("ANALYTICS_DATABASE_URL"), os.environ.get("APP_DATABASE_URL")
    if not analytics or not app:
        print("ANALYTICS_DATABASE_URL and APP_DATABASE_URL must be set", file=sys.stderr)
        return 2
    if args.command == "record-replays":
        ids = record_replays(analytics_dsn=analytics, app_dsn=app)
        print(f"recorded {len(ids)} replays: {', '.join(ids)}")
        return 0
    if args.command == "benchmark":
        bench = run_benchmark(
            load_corpus(args.corpus),
            analytics_dsn=analytics,
            app_dsn=app,
            live_provider=live_provider,
            stop_after_rate_limited=args.stop_after_rate_limited,
        )
        out_dir = args.out_dir or Path(
            "benchmarks/orchestration/v1/live" if args.live else "benchmarks/orchestration/v1"
        )
        json_path, md_path = write_benchmark(bench, out_dir)
        print(f"{bench.recommendation}: {bench.rationale}")
        print(f"wrote {json_path} and {md_path}")
        if bench.stopped_early:
            print(
                f"STOPPED EARLY: {bench.stopped_early} after {bench.stopped_after}; "
                f"{len(bench.not_run)} cases not run"
            )
        return int(
            args.live and (bool(bench.stopped_early) or any(not run.success for run in bench.runs))
        )
    report = run_corpus(
        load_corpus(args.corpus),
        analytics_dsn=analytics,
        app_dsn=app,
        live_provider=live_provider,
        stop_after_rate_limited=args.stop_after_rate_limited,
    )
    if args.out:
        args.out.write_bytes((report.model_dump_json(indent=2) + "\n").encode("utf-8"))
    print(
        f"{report.dataset_version} @ {report.git_sha[:7]} prompt {report.prompt_version}: "
        f"{report.passed}/{report.total} passed"
        + (
            f"; live outcomes {report.live_passed}/{report.live_scored}"
            f" ({len(report.live_unscored)} unscored)"
            if report.mode == "live"
            else ""
        )
    )
    for result in report.results:
        if not result.passed:
            print(f"FAIL {result.case_id} trace={result.trace_id}: {'; '.join(result.failures)}")
    if report.stopped_early:
        print(
            f"STOPPED EARLY: {report.stopped_early} after {report.stopped_after}; "
            f"{len(report.not_run)} workflow cases not run"
        )
    return 0 if report.failed == 0 and not report.stopped_early else 1


if __name__ == "__main__":
    raise SystemExit(main())
