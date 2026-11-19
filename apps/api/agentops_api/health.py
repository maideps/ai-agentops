"""Liveness and readiness endpoints."""

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/health", tags=["health"])


class LiveResponse(BaseModel):
    status: Literal["ok"]


class ReadyResponse(BaseModel):
    status: Literal["ready", "not_ready"]
    checks: dict[str, Literal["ok", "failed"]]


@router.get("/live")
def live() -> LiveResponse:
    return LiveResponse(status="ok")


@router.get("/ready")
def ready() -> ReadyResponse:
    # No dependencies yet; feat-002 adds the database check.
    checks: dict[str, Literal["ok", "failed"]] = {}
    status: Literal["ready", "not_ready"] = (
        "ready" if all(result == "ok" for result in checks.values()) else "not_ready"
    )
    return ReadyResponse(status=status, checks=checks)
