"""Shared setup for the feat-004 workflow tests: mock model scripts from fixtures/llm."""

import asyncio
import time
from collections.abc import Callable
from pathlib import Path

import psycopg

from agentops_agents.state import RunDetail, RunLimits, TaskRequest
from agentops_agents.workflow import RunDependencies, run_task
from agentops_core.llm import LLMGateway, ModelCapabilities, ModelRequest, ModelResponse
from agentops_llm.mock import MOCK_MODEL, MockLLMProvider
from agentops_retrieval.embedding import HashingEmbedder

REPO = Path(__file__).resolve().parents[3]
LLM_FIXTURES = REPO / "fixtures" / "llm"
REPLAYS = REPO / "fixtures" / "replays"

SAMPLE_RUN_ID = "run-sample-q3-declines"
SAMPLE_TASK = (
    "Analyze quarterly sales, identify the three largest declines from 2026-Q2 to 2026-Q3, "
    "consult relevant company policies, prepare a cited executive summary, and propose a "
    "follow-up ticket."
)
FIXED_TRACE_ID = "0" * 31 + "1"


class CountingProvider:
    """Wraps the mock to count how often the model was really called."""

    name = "mock"

    def __init__(self, inner: MockLLMProvider) -> None:
        self.inner = inner
        self.calls = 0

    def capabilities(self, model: str) -> ModelCapabilities:
        return self.inner.capabilities(model)

    async def generate(self, request: ModelRequest, model: str) -> ModelResponse:
        self.calls += 1
        return await self.inner.generate(request, model)


def run(
    analytics_dsn: str,
    *,
    run_id: str = SAMPLE_RUN_ID,
    task_text: str = SAMPLE_TASK,
    user_id: str = "user-a-analyst",
    tenant_id: str = "demo-a",
    limits: RunLimits | None = None,
    clock: Callable[[], float] | None = None,
) -> tuple[RunDetail, CountingProvider]:
    provider = CountingProvider(MockLLMProvider.from_directory(LLM_FIXTURES))
    deps = RunDependencies(
        gateway=LLMGateway(provider, MOCK_MODEL),
        llm_provider=provider.name,
        llm_model=MOCK_MODEL,
        connect=lambda: psycopg.connect(analytics_dsn),
        embedder=HashingEmbedder(),
        limits=limits or RunLimits(),
        new_trace_id=lambda: FIXED_TRACE_ID,
        clock=clock if clock is not None else time.monotonic,
    )
    request = TaskRequest(run_id=run_id, tenant_id=tenant_id, user_id=user_id, task_text=task_text)
    return asyncio.run(run_task(request, deps)), provider
