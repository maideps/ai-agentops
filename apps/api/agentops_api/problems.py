"""Problem-details errors (spec 11.1): code, message, request_id; never a stack trace."""

import uuid
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from agentops_telemetry.tracing import span


class ProblemError(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


def install(app: FastAPI) -> None:
    @app.middleware("http")
    async def request_context(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request.state.request_id = uuid.uuid4().hex
        with span("http.request", {"http.method": request.method}) as current:
            response = await call_next(request)
            route = request.scope.get("route")
            current.set_attribute("http.route", getattr(route, "path", "unmatched"))
            current.set_attribute("http.status_code", response.status_code)
        response.headers["X-Request-ID"] = request.state.request_id
        return response

    @app.exception_handler(ProblemError)
    async def problem(request: Request, error: ProblemError) -> JSONResponse:
        return JSONResponse(
            status_code=error.status,
            content={
                "code": error.code,
                "message": error.message,
                "request_id": getattr(request.state, "request_id", ""),
            },
        )
