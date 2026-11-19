"""Serve the MCP tools over stdio for one principal and run.

    APP_DATABASE_URL=... uv run python -m agentops_tools serve \\
        --tenant demo-a --user user-a-analyst --run-id run-123

Meant to be spawned by the trusted backend, which sets the principal; the model only ever
sees the tools. Uses the least-privilege gateway login in APP_DATABASE_URL.
"""

import argparse
import asyncio
import os
import sys

import psycopg

from agentops_retrieval.embedding import HashingEmbedder
from agentops_tools.gateway import CallContext, ToolGateway
from agentops_tools.mcp_server import build_server


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m agentops_tools")
    parser.add_argument("command", choices=["serve"])
    parser.add_argument("--tenant", required=True)
    parser.add_argument("--user", required=True)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args(argv)

    url = os.environ.get("APP_DATABASE_URL")
    if not url:
        print("APP_DATABASE_URL is not set", file=sys.stderr)
        return 2
    gateway = ToolGateway(connect=lambda: psycopg.connect(url), embedder=HashingEmbedder())
    ctx = CallContext(tenant_id=args.tenant, user_id=args.user, run_id=args.run_id)
    asyncio.run(build_server(gateway, ctx).run_stdio_async())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
