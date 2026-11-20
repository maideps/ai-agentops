"""POST /v1/runs/{run_id}/feedback (FR-014).

Phase 1 uses a scoped demo identity (spec section 9): a configured bearer token stands for one
configured demo user. No token configured means no writes.
"""

from typing import Annotated, Literal

import psycopg
from fastapi import APIRouter, Header, Path, Request
from pydantic import BaseModel, ConfigDict, Field

from agentops_api.auth import demo_principal
from agentops_api.problems import ProblemError
from agentops_api.settings import Settings
from agentops_data.access import UnknownPrincipalError
from agentops_data.feedback import record_feedback

router = APIRouter(prefix="/v1/runs", tags=["feedback"])

RunId = Annotated[str, Path(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")]


class FeedbackIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rating: Literal["up", "down"]
    comment: str | None = Field(default=None, max_length=500)
    eval_case_id: str | None = Field(default=None, pattern=r"^[a-z0-9][a-z0-9-]{0,63}$")


class FeedbackOut(BaseModel):
    feedback_id: str
    run_id: str


@router.post("/{run_id}/feedback", status_code=201)
def submit_feedback(
    run_id: RunId,
    body: FeedbackIn,
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> FeedbackOut:
    settings: Settings = request.app.state.settings
    tenant_id, user_id = demo_principal(settings, authorization)
    if settings.app_database_url is None:
        raise ProblemError(503, "STORAGE_NOT_CONFIGURED", "APP_DATABASE_URL is not set")
    try:
        with psycopg.connect(settings.app_database_url.get_secret_value()) as conn:
            feedback_id = record_feedback(
                conn,
                tenant_id=tenant_id,
                user_id=user_id,
                run_id=run_id,
                rating=body.rating,
                comment=body.comment,
                eval_case_id=body.eval_case_id,
            )
    except UnknownPrincipalError:
        raise ProblemError(403, "FORBIDDEN", "the demo identity is not a known user") from None
    return FeedbackOut(feedback_id=feedback_id, run_id=run_id)
