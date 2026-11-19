"""LiteLLM SDK adapter (FR-009). The only module that talks to LiteLLM (arch-101).

Never selected unless LLM_MODE and ENABLE_LIVE_LLM opt in (see ``selection``).
"""

import json
import time
from collections.abc import Awaitable, Callable
from typing import Any

import litellm
import openai
from litellm import exceptions as llx

from agentops_core.llm import (
    CapabilityRegistry,
    LLMError,
    LLMErrorCode,
    ModelCapabilities,
    ModelRequest,
    ModelResponse,
    ToolCall,
)

CompletionFn = Callable[..., Awaitable[Any]]

# Order matters: Timeout subclasses APIConnectionError, and the 400-family errors share bases.
_ERROR_MAP: tuple[tuple[tuple[type[BaseException], ...], LLMErrorCode], ...] = (
    ((llx.Timeout,), LLMErrorCode.TIMEOUT),
    ((llx.RateLimitError,), LLMErrorCode.RATE_LIMITED),
    ((llx.AuthenticationError, llx.PermissionDeniedError), LLMErrorCode.AUTH_FAILED),
    ((llx.UnsupportedParamsError,), LLMErrorCode.CAPABILITY_UNSUPPORTED),
    ((llx.BudgetExceededError,), LLMErrorCode.BUDGET_EXCEEDED),
    ((llx.BadRequestError, llx.NotFoundError), LLMErrorCode.INVALID_REQUEST),
    ((openai.APIError,), LLMErrorCode.PROVIDER_UNAVAILABLE),
)


def _to_llm_error(exc: BaseException, provider: str) -> LLMError:
    for types, code in _ERROR_MAP:
        if isinstance(exc, types):
            # Only the exception type: provider messages can echo request data or key fragments.
            return LLMError(code, f"provider error {type(exc).__name__}", provider=provider)
    raise TypeError(type(exc).__name__)  # unreachable: callers catch only mapped types


class LiteLLMProvider:
    name = "litellm"

    def __init__(
        self,
        registry: CapabilityRegistry,
        *,
        completion: CompletionFn | None = None,
        api_key: str | None = None,
        num_retries: int = 0,
    ) -> None:
        self._registry = registry
        self._completion: CompletionFn = (
            completion if completion is not None else litellm.acompletion
        )
        self._api_key = api_key
        self._num_retries = num_retries

    def capabilities(self, model: str) -> ModelCapabilities:
        return self._registry.get(model)

    async def generate(self, request: ModelRequest, model: str) -> ModelResponse:
        provider = self._registry.get(model).provider
        started = time.perf_counter()
        try:
            raw = await self._completion(**self._kwargs(request, model))
        except (openai.APIError, llx.BudgetExceededError) as exc:
            raise _to_llm_error(exc, provider) from None
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        return _normalize(raw, provider=provider, model=model, elapsed_ms=elapsed_ms)

    def _kwargs(self, request: ModelRequest, model: str) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": [message.model_dump(exclude_none=True) for message in request.messages],
            "max_tokens": request.max_output_tokens,
            "timeout": request.timeout_seconds,
            "num_retries": self._num_retries,
        }
        if self._api_key is not None:
            kwargs["api_key"] = self._api_key
        if request.tools:
            kwargs["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.parameters,
                    },
                }
                for tool in request.tools
            ]
        if request.response_schema is not None:
            kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": request.response_schema.name,
                    "schema": request.response_schema.json_schema,
                    "strict": True,
                },
            }
        return kwargs


def _normalize(raw: Any, *, provider: str, model: str, elapsed_ms: int) -> ModelResponse:
    message = raw.choices[0].message
    tool_calls: list[ToolCall] = []
    for call in message.tool_calls or []:
        try:
            arguments = json.loads(call.function.arguments or "{}")
        except json.JSONDecodeError:
            arguments = None
        if not isinstance(arguments, dict):
            raise LLMError(
                LLMErrorCode.INVALID_RESPONSE,
                f"tool call {call.function.name!r} arguments are not a JSON object",
                provider=provider,
            )
        tool_calls.append(ToolCall(id=call.id, name=call.function.name, arguments=arguments))
    usage = getattr(raw, "usage", None)
    return ModelResponse(
        text=message.content,
        tool_calls=tool_calls,
        provider=provider,
        model=model,
        prompt_tokens=getattr(usage, "prompt_tokens", None),
        completion_tokens=getattr(usage, "completion_tokens", None),
        elapsed_ms=elapsed_ms,
    )
