"""Run one task in mock mode and print its run detail as JSON.

    uv run python -m agentops_agents run --run-id run-sample-q3-declines \\
        --tenant demo-a --user user-a-analyst "Analyze quarterly sales ..."

Uses the scripted mock model from ``fixtures/llm/`` (keyed by run id) and the read-only
analytics login in ANALYTICS_DATABASE_URL. No hosted model is ever called from here.
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path

import psycopg

from agentops_agents.state import TaskRequest
from agentops_agents.workflow import RunDependencies, run_task
from agentops_core.llm import LLMGateway
from agentops_llm.mock import MOCK_MODEL, MockLLMProvider
from agentops_retrieval.embedding import HashingEmbedder


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m agentops_agents")
    parser.add_argument("command", choices=["run"])
    parser.add_argument("task_text")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--tenant", required=True)
    parser.add_argument("--user", required=True)
    parser.add_argument("--fixtures", type=Path, default=Path("fixtures/llm"))
    args = parser.parse_args(argv)

    url = os.environ.get("ANALYTICS_DATABASE_URL")
    if not url:
        print("ANALYTICS_DATABASE_URL is not set", file=sys.stderr)
        return 2
    provider = MockLLMProvider.from_directory(args.fixtures)
    deps = RunDependencies(
        gateway=LLMGateway(provider, MOCK_MODEL),
        llm_provider=provider.name,
        llm_model=MOCK_MODEL,
        connect=lambda: psycopg.connect(url),
        embedder=HashingEmbedder(),
    )
    request = TaskRequest(
        run_id=args.run_id, tenant_id=args.tenant, user_id=args.user, task_text=args.task_text
    )
    detail = asyncio.run(run_task(request, deps))
    print(detail.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
