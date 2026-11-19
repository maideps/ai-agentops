"""FastAPI application factory.

Run locally: ``uv run uvicorn agentops_api.app:create_app --factory``
"""

import logging
from typing import TextIO

from fastapi import FastAPI

from agentops_api import __version__, problems
from agentops_api.feedback import router as feedback_router
from agentops_api.health import router as health_router
from agentops_api.logging import ROOT_LOGGER, configure_logging
from agentops_api.settings import Settings
from agentops_telemetry.tracing import configure_tracing

logger = logging.getLogger(f"{ROOT_LOGGER}.api")


def create_app(settings: Settings | None = None, *, log_stream: TextIO | None = None) -> FastAPI:
    settings = settings if settings is not None else Settings()
    configure_logging(settings.log_level, log_stream)
    if settings.langfuse_enabled:  # explicit opt-in; fails fast without LANGFUSE_* keys
        configure_tracing(service_name="ai-agentops-api", langfuse_enabled=True)

    app = FastAPI(title="AI AgentOps API", version=__version__)
    app.state.settings = settings
    problems.install(app)
    app.include_router(health_router)
    app.include_router(feedback_router)

    logger.info(
        "app.created",
        extra={
            "fields": {
                "app_env": settings.app_env,
                "llm_mode": settings.llm_mode,
                "enable_live_llm": settings.enable_live_llm,
            }
        },
    )
    return app
