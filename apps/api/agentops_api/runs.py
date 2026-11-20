"""POST /v1/runs: the optional live mode of the demo (feat-009, D-013).

Authenticated with the demo token and capped per user per day. In mock mode (the default) the
model's replies come from a named script in fixtures/llm, so a run is real (database, policy,
gateway, citations) but its model turns are scripted. Hosted models need LLM_MODE plus
ENABLE_LIVE_LLM and a registered model (D-005); replay mode refuses live runs.
"""

import re
import uuid
from pathlib import Path
from typing import Annotated, Any

import psycopg
from fastapi import APIRouter, Header, Request
from pydantic import BaseModel, ConfigDict, Field

from agentops_agents.state import RunLimits, TaskRequest
from agentops_agents.workflow import RunDependencies, run_task
from agentops_api.auth import demo_principal
from agentops_api.problems import ProblemError
from agentops_api.settings import Settings
from agentops_core.aio import run as run_async
from agentops_core.llm import CapabilityRegistry, LLMGateway, LLMProvider
from agentops_data.access import UnknownPrincipalError
from agentops_data.quota import QuotaExceededError, claim_run
from agentops_llm.mock import MockLLMProvider, MockScript
from agentops_llm.selection import select_provider
from agentops_retrieval.embedding import HashingEmbedder
from agentops_tools.gateway import ToolGateway

router = APIRouter(prefix="/v1/runs", tags=["runs"])
SCRIPT_NAME = r"^[a-z0-9][a-z0-9-]{0,63}$"


class RunIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_text: str = Field(min_length=1, max_length=2000)
    # Mock mode only: which scripted model replies to use (a file in fixtures/llm).
    script: str = Field(pattern=SCRIPT_NAME)


def new_run_id() -> str:
    return f"api-{uuid.uuid4()}"


def _mock_provider(scripts_dir: Path, script: str, run_id: str) -> MockLLMProvider:
    if not re.fullmatch(SCRIPT_NAME, script):  # defense in depth; the body model checks too
        raise ProblemError(422, "INVALID_SCRIPT", "invalid script name")
    path = scripts_dir / f"{script}.json"
    if not path.is_file():
        raise ProblemError(404, "SCRIPT_NOT_FOUND", f"no mock script named {script!r}")
    loaded = MockScript.model_validate_json(path.read_text(encoding="utf-8"))
    return MockLLMProvider(scripts=[loaded.model_copy(update={"run_id": run_id})])


def _limits(settings: Settings) -> RunLimits:
    return RunLimits(
        max_llm_calls=settings.max_llm_calls_per_run,
        max_tool_calls=settings.max_tool_calls_per_run,
        max_graph_steps=settings.max_graph_steps,
        max_run_seconds=settings.max_run_seconds,
        max_output_tokens=settings.max_output_tokens,
    )


@router.post("", status_code=201)
def create_run(
    body: RunIn, request: Request, authorization: Annotated[str | None, Header()] = None
) -> dict[str, Any]:
    settings: Settings = request.app.state.settings
    tenant_id, user_id = demo_principal(settings, authorization)
    if settings.llm_mode == "replay":
        raise ProblemError(503, "LIVE_DISABLED", "this deployment serves replays only")
    run_id = new_run_id()
    provider: LLMProvider = select_provider(
        settings.llm_mode,
        enable_live_llm=settings.enable_live_llm,
        mock_factory=lambda: _mock_provider(settings.mock_scripts_dir, body.script, run_id),
        live_factory=lambda: _live_provider(),
    )
    if settings.app_database_url is None or settings.analytics_database_url is None:
        raise ProblemError(503, "STORAGE_NOT_CONFIGURED", "database URLs are not set")
    app_url = settings.app_database_url.get_secret_value()
    analytics_url = settings.analytics_database_url.get_secret_value()
    try:
        with psycopg.connect(app_url) as conn:
            claim_run(
                conn,
                tenant_id=tenant_id,
                user_id=user_id,
                run_id=run_id,
                cap=settings.max_requests_per_demo_user,
            )
    except QuotaExceededError:
        raise ProblemError(429, "QUOTA_EXCEEDED", "daily run limit reached") from None
    except UnknownPrincipalError:
        raise ProblemError(403, "FORBIDDEN", "the demo identity is not a known user") from None

    embedder = HashingEmbedder()
    deps = RunDependencies(
        gateway=LLMGateway(provider, settings.llm_model),
        llm_provider=provider.name,
        llm_model=settings.llm_model,
        connect=lambda: psycopg.connect(analytics_url),
        embedder=embedder,
        tool_gateway=ToolGateway(connect=lambda: psycopg.connect(app_url), embedder=embedder),
        limits=_limits(settings),
    )
    task = TaskRequest(
        run_id=run_id, tenant_id=tenant_id, user_id=user_id, task_text=body.task_text
    )
    detail = run_async(run_task(task, deps))
    return detail.model_dump(mode="json")


def _live_provider() -> LLMProvider:
    """Hosted models go through LiteLLM; none is registered yet, so every model is refused
    before any provider call (MODEL_CAPABILITY_UNSUPPORTED, D-005)."""
    from agentops_llm.litellm_provider import LiteLLMProvider

    return LiteLLMProvider(registry=CapabilityRegistry([]))
