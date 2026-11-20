"""Runs over HTTP (feat-009, feat-011; D-013, D-015).

- POST /v1/runs: run a task for the demo user, capped per day. In mock mode (the default) the
  model's replies come from a named script in fixtures/llm; hosted models need LLM_MODE plus
  ENABLE_LIVE_LLM and a registered model (D-005); replay mode refuses. With propose_followup the
  run pauses at awaiting_approval with a bound proposal.
- GET /v1/runs/{run_id}: the run's current sanitized detail, from its checkpoint.
- POST /v1/runs/{run_id}/approvals/{approval_id}: approve or reject the proposal through the
  gateway, then resume the run. Resuming makes no model call.

Every run is checkpointed with a saver scoped to the demo user's tenant (D-014), so another
tenant's run is simply not found.
"""

import re
import uuid
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Annotated, Any, Literal

import psycopg
from fastapi import APIRouter, Header, Request
from fastapi import Path as PathParam
from pydantic import BaseModel, ConfigDict, Field

from agentops_agents.checkpoints import postgres_checkpointer
from agentops_agents.state import RunDetail, RunLimits, TaskRequest
from agentops_agents.workflow import RunDependencies, load_run, resume_task, run_task
from agentops_api.auth import demo_principal
from agentops_api.problems import ProblemError
from agentops_api.settings import Settings
from agentops_core.aio import run as run_async
from agentops_core.llm import CapabilityRegistry, LLMGateway, LLMProvider
from agentops_data.access import UnknownPrincipalError
from agentops_data.quota import QuotaExceededError, claim_run
from agentops_llm.mock import MockLLMProvider, MockScript
from agentops_llm.selection import ReplayProvider, select_provider
from agentops_retrieval.embedding import HashingEmbedder
from agentops_tools.gateway import CallContext, GatewayDenied, ToolGateway

router = APIRouter(prefix="/v1/runs", tags=["runs"])
SCRIPT_NAME = r"^[a-z0-9][a-z0-9-]{0,63}$"
RunId = Annotated[str, PathParam(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")]
ApprovalId = Annotated[
    str, PathParam(pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
]
Authorization = Annotated[str | None, Header()]

# Gateway refusals as HTTP statuses: identity problems are 403, state conflicts 409.
_DENIAL_STATUS = {
    "APPROVAL_NOT_FOUND": 404,
    "APPROVAL_PRINCIPAL_MISMATCH": 403,
    "APPROVAL_RUN_MISMATCH": 403,
    "UNKNOWN_PRINCIPAL": 403,
    "APPROVAL_ALREADY_DECIDED": 409,
    "APPROVAL_EXPIRED": 409,
}


class RunIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_text: str = Field(min_length=1, max_length=2000)
    # Mock mode only: which scripted model replies to use (a file in fixtures/llm).
    script: str = Field(pattern=SCRIPT_NAME)
    propose_followup: bool = False


class DecisionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["approve", "reject"]


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


def _live_provider() -> LLMProvider:
    """Hosted models go through LiteLLM; none is registered yet, so every model is refused
    before any provider call (MODEL_CAPABILITY_UNSUPPORTED, D-005)."""
    from agentops_llm.litellm_provider import LiteLLMProvider

    return LiteLLMProvider(registry=CapabilityRegistry([]))


def _storage(settings: Settings) -> tuple[str, str]:
    if settings.app_database_url is None or settings.analytics_database_url is None:
        raise ProblemError(503, "STORAGE_NOT_CONFIGURED", "database URLs are not set")
    return (
        settings.app_database_url.get_secret_value(),
        settings.analytics_database_url.get_secret_value(),
    )


def _in_tenant(
    settings: Settings,
    tenant_id: str,
    provider: LLMProvider,
    step: Callable[[RunDependencies], Awaitable[RunDetail]],
) -> RunDetail:
    """Run ``step`` with dependencies whose checkpointer is scoped to ``tenant_id``."""
    app_url, analytics_url = _storage(settings)
    embedder = HashingEmbedder()

    async def go() -> RunDetail:
        async with postgres_checkpointer(app_url, tenant_id=tenant_id) as saver:
            deps = RunDependencies(
                gateway=LLMGateway(provider, settings.llm_model),
                llm_provider=provider.name,
                llm_model=settings.llm_model,
                connect=lambda: psycopg.connect(analytics_url),
                embedder=embedder,
                tool_gateway=ToolGateway(
                    connect=lambda: psycopg.connect(app_url), embedder=embedder
                ),
                limits=RunLimits(
                    max_llm_calls=settings.max_llm_calls_per_run,
                    max_tool_calls=settings.max_tool_calls_per_run,
                    max_graph_steps=settings.max_graph_steps,
                    max_run_seconds=settings.max_run_seconds,
                    max_output_tokens=settings.max_output_tokens,
                ),
                checkpointer=saver,
            )
            return await step(deps)

    return run_async(go())


@router.post("", status_code=201)
def create_run(
    body: RunIn, request: Request, authorization: Authorization = None
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
        live_factory=_live_provider,
    )
    app_url, _ = _storage(settings)
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

    task = TaskRequest(
        run_id=run_id,
        tenant_id=tenant_id,
        user_id=user_id,
        task_text=body.task_text,
        propose_followup=body.propose_followup,
    )
    detail = _in_tenant(settings, tenant_id, provider, lambda deps: run_task(task, deps))
    return detail.model_dump(mode="json")


@router.get("/{run_id}")
def get_run(run_id: RunId, request: Request, authorization: Authorization = None) -> dict[str, Any]:
    settings: Settings = request.app.state.settings
    tenant_id, _ = demo_principal(settings, authorization)
    try:
        detail = _in_tenant(
            settings,
            tenant_id,
            ReplayProvider(),
            lambda deps: load_run(run_id, deps, tenant_id=tenant_id),
        )
    except LookupError:
        raise ProblemError(404, "RUN_NOT_FOUND", f"run {run_id!r} not found") from None
    return detail.model_dump(mode="json")


@router.post("/{run_id}/approvals/{approval_id}")
def decide_approval(
    run_id: RunId,
    approval_id: ApprovalId,
    body: DecisionIn,
    request: Request,
    authorization: Authorization = None,
) -> dict[str, Any]:
    settings: Settings = request.app.state.settings
    tenant_id, user_id = demo_principal(settings, authorization)
    app_url, _ = _storage(settings)
    approve = body.decision == "approve"
    get_run(run_id, request, authorization)  # 404 for unknown runs and other tenants' runs

    ctx = CallContext(tenant_id=tenant_id, user_id=user_id, run_id=run_id)
    gateway = ToolGateway(connect=lambda: psycopg.connect(app_url), embedder=HashingEmbedder())
    try:
        gateway.decide(ctx, approval_id, approve=approve)
    except GatewayDenied as denied:
        status = _DENIAL_STATUS.get(denied.reason_code, 422)
        raise ProblemError(status, denied.reason_code, "the approval cannot be decided") from None

    # A provider that refuses every call: resuming must never call the model.
    try:
        detail = _in_tenant(
            settings,
            tenant_id,
            ReplayProvider(),
            lambda deps: resume_task(run_id, deps, tenant_id=tenant_id, approved=approve),
        )
    except LookupError:
        raise ProblemError(409, "RUN_NOT_AWAITING_APPROVAL", "the run is not paused") from None
    return detail.model_dump(mode="json")
