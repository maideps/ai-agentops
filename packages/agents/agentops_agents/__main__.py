"""Run one task in mock mode and print its run detail as JSON; or set up checkpoint tables.

    uv run python -m agentops_agents setup-checkpoints   # schema owner in DATABASE_URL
    uv run python -m agentops_agents run --run-id run-sample-q3-declines \\
        --tenant demo-a --user user-a-analyst "Analyze quarterly sales ..."

Uses the scripted mock model from ``fixtures/llm/`` (keyed by run id) and the read-only
analytics login in ANALYTICS_DATABASE_URL; tool reads go through the gateway login in
APP_DATABASE_URL. No hosted model is ever called from here.
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path

import psycopg

from agentops_agents.checkpoints import setup_checkpoints
from agentops_agents.state import TaskRequest
from agentops_agents.workflow import RunDependencies, run_task
from agentops_core.llm import LLMGateway
from agentops_llm.mock import MOCK_MODEL, MockLLMProvider
from agentops_retrieval.embedding import HashingEmbedder
from agentops_tools.gateway import ToolGateway


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m agentops_agents")
    parser.add_argument("command", choices=["run", "setup-checkpoints"])
    parser.add_argument("task_text", nargs="?")
    parser.add_argument("--run-id")
    parser.add_argument("--tenant")
    parser.add_argument("--user")
    parser.add_argument("--fixtures", type=Path, default=Path("fixtures/llm"))
    args = parser.parse_args(argv)

    if args.command == "setup-checkpoints":
        owner = os.environ.get("DATABASE_URL")
        if not owner:
            print("DATABASE_URL (schema owner) is not set", file=sys.stderr)
            return 2
        print("checkpoint tables:", ", ".join(setup_checkpoints(owner)))
        return 0
    if not (args.task_text and args.run_id and args.tenant and args.user):
        parser.error("run needs task_text, --run-id, --tenant and --user")

    url = os.environ.get("ANALYTICS_DATABASE_URL")
    app_url = os.environ.get("APP_DATABASE_URL")
    if not url or not app_url:
        print("ANALYTICS_DATABASE_URL and APP_DATABASE_URL must be set", file=sys.stderr)
        return 2
    provider = MockLLMProvider.from_directory(args.fixtures)
    deps = RunDependencies(
        gateway=LLMGateway(provider, MOCK_MODEL),
        llm_provider=provider.name,
        llm_model=MOCK_MODEL,
        connect=lambda: psycopg.connect(url),
        embedder=HashingEmbedder(),
        tool_gateway=ToolGateway(
            connect=lambda: psycopg.connect(app_url), embedder=HashingEmbedder()
        ),
    )
    request = TaskRequest(
        run_id=args.run_id, tenant_id=args.tenant, user_id=args.user, task_text=args.task_text
    )
    detail = asyncio.run(run_task(request, deps))
    print(detail.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
