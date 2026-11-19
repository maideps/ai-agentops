"""Liveness and readiness endpoints."""

import logging
from typing import Literal

import psycopg
from fastapi import APIRouter, Request, Response
from pydantic import BaseModel

from agentops_api.logging import ROOT_LOGGER
from agentops_api.settings import Settings

router = APIRouter(prefix="/health", tags=["health"])
logger = logging.getLogger(f"{ROOT_LOGGER}.health")

CheckResult = Literal["ok", "failed"]


class LiveResponse(BaseModel):
    status: Literal["ok"]


class ReadyResponse(BaseModel):
    status: Literal["ready", "not_ready"]
    checks: dict[str, CheckResult]


@router.get("/live")
def live() -> LiveResponse:
    return LiveResponse(status="ok")


def _check_database(url: str) -> CheckResult:
    try:
        with psycopg.connect(url, connect_timeout=2) as conn:
            conn.execute("SELECT 1")
    except psycopg.Error as exc:
        # The error type only: messages can contain the host, user or other URL parts.
        logger.warning("health.database_failed", extra={"fields": {"error": type(exc).__name__}})
        return "failed"
    return "ok"


@router.get("/ready", responses={503: {"model": ReadyResponse}})
def ready(request: Request, response: Response) -> ReadyResponse:
    settings: Settings = request.app.state.settings
    checks: dict[str, CheckResult] = {}
    if settings.database_url is not None:
        checks["database"] = _check_database(settings.database_url.get_secret_value())
    is_ready = all(result == "ok" for result in checks.values())
    if not is_ready:
        response.status_code = 503
    return ReadyResponse(status="ready" if is_ready else "not_ready", checks=checks)
