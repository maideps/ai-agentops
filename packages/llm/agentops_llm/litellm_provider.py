"""LiteLLM SDK adapter (FR-009). The only module that talks to LiteLLM (arch-101).

Never selected unless LLM_MODE and ENABLE_LIVE_LLM opt in (see ``selection``).
"""

import asyncio
import json
import math
import threading
import time
from collections.abc import Awaitable, Callable, Sequence
from decimal import Decimal, InvalidOperation
from functools import cache
from importlib.resources import files
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
CostEstimator = Callable[[str, int, int], float]


@cache
def _price_map() -> dict[str, Any]:
    return dict(
        json.loads(
            files("litellm")
            .joinpath("model_prices_and_context_window_backup.json")
            .read_text(encoding="utf-8")
        )
    )


def _litellm_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """USD cost of the given tokens from LiteLLM's bundled price map (offline)."""
    prices = _price_map()[model]
    input_rate = Decimal(str(prices["input_cost_per_token"]))
    output_rate = Decimal(str(prices["output_cost_per_token"]))
    if any(not rate.is_finite() or rate < 0 for rate in (input_rate, output_rate)):
        raise ValueError("invalid model prices")
    return float(input_rate * prompt_tokens + output_rate * completion_tokens)


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


# feat-015: failures where the request most likely never ran, worth another attempt. Timeouts
# subclass APIConnectionError but may have been billed; rate limits need a longer wait.
def _is_transient(exc: BaseException) -> bool:
    if isinstance(exc, llx.Timeout):
        return False
    return isinstance(exc, (llx.ServiceUnavailableError, llx.APIConnectionError))


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
        budget_usd: float | None = None,
        total_budget_usd: float | None = None,
        cost_estimator: CostEstimator | None = None,
        transient_retries: int = 2,
        backoff_seconds: Sequence[float] = (1.0, 2.0),
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._registry = registry
        self._completion: CompletionFn = (
            completion if completion is not None else litellm.acompletion
        )
        self._api_key = api_key
        self._num_retries = num_retries
        for budget in (budget_usd, total_budget_usd):
            if budget is not None and (not math.isfinite(budget) or budget < 0):
                raise LLMError(
                    LLMErrorCode.INVALID_REQUEST, "budget must be finite and nonnegative"
                )
        if (budget_usd is not None or total_budget_usd is not None) and num_retries:
            raise LLMError(LLMErrorCode.INVALID_REQUEST, "budgeted calls cannot retry")
        self._budget_usd = Decimal(str(budget_usd)) if budget_usd is not None else None
        self._total_budget_usd = (
            Decimal(str(total_budget_usd)) if total_budget_usd is not None else None
        )
        self._cost_estimator: CostEstimator = (
            cost_estimator if cost_estimator is not None else _litellm_cost
        )
        if transient_retries < 0 or len(backoff_seconds) < transient_retries:
            raise LLMError(LLMErrorCode.INVALID_REQUEST, "each retry needs a backoff delay")
        self._transient_retries = transient_retries
        self._backoff_seconds = tuple(backoff_seconds)
        self._sleep = sleep
        self._retries: dict[str, int] = {}
        self._spent_usd: dict[str, Decimal] = {}
        self._reserved_usd: dict[str, Decimal] = {}
        self._reserved_total = Decimal(0)
        self._budget_lock = threading.Lock()

    def spent_usd(self, run_id: str) -> float:
        """Cost of reported usage at the bundled rates, not a provider invoice."""
        return float(self._spent_usd.get(run_id, Decimal(0)))

    def reserved_usd(self, run_id: str) -> float:
        return float(self._reserved_usd.get(run_id, Decimal(0)))

    def retries(self, run_id: str) -> int:
        """Transient-failure retries dispatched for this run (feat-015)."""
        return self._retries.get(run_id, 0)

    def capabilities(self, model: str) -> ModelCapabilities:
        return self._registry.get(model)

    async def generate(self, request: ModelRequest, model: str) -> ModelResponse:
        provider = self._registry.get(model).provider
        budgeted = self._budget_usd is not None or self._total_budget_usd is not None
        attempt = 0
        last: LLMError | None = None
        while True:
            started = time.perf_counter()
            try:
                if budgeted:
                    # Every attempt reserves like a new call: a refused one may still be billed.
                    self._reserve(request, model, provider)
                if attempt:
                    with self._budget_lock:
                        self._retries[request.run_id] = self._retries.get(request.run_id, 0) + 1
                raw = await self._completion(**self._kwargs(request, model))
                break
            except LLMError as refused:
                if last is None:
                    raise
                # The budget cannot cover another attempt: report the provider failure.
                raise last from refused
            except (openai.APIError, llx.BudgetExceededError) as exc:
                last = _to_llm_error(exc, provider)
                if attempt >= self._transient_retries or not _is_transient(exc):
                    raise last from None
            await self._sleep(self._backoff_seconds[attempt])
            attempt += 1
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        response = _normalize(raw, provider=provider, model=model, elapsed_ms=elapsed_ms)
        if budgeted:
            response = self._account(request, model, response)
        if getattr(raw.choices[0], "finish_reason", None) == "length":
            raise LLMError(
                LLMErrorCode.OUTPUT_TRUNCATED,
                f"reply stopped at max_output_tokens={request.max_output_tokens}",
                provider=provider,
            )
        return response

    def _cost(self, model: str, prompt_tokens: int, completion_tokens: int) -> Decimal:
        try:
            cost = self._cost_estimator(model, prompt_tokens, completion_tokens)
        except (KeyError, TypeError, ValueError, OverflowError, InvalidOperation):
            raise LLMError(LLMErrorCode.BUDGET_EXCEEDED, "model pricing is unavailable") from None
        if not math.isfinite(cost) or cost < 0:
            raise LLMError(LLMErrorCode.BUDGET_EXCEEDED, "model pricing is unbounded")
        return Decimal(str(cost))

    def _reserve(self, request: ModelRequest, model: str, provider: str) -> None:
        # The full input window includes tools/schema overhead; word estimates cannot bound it.
        # Never refund: timeouts, cancellation and malformed responses may still be billed.
        bound = self._cost(
            model, self._registry.get(model).max_context_tokens, request.max_output_tokens
        )
        with self._budget_lock:
            per_run = self._reserved_usd.get(request.run_id, Decimal(0)) + bound
            total = self._reserved_total + bound
            if (self._budget_usd is not None and per_run > self._budget_usd) or (
                self._total_budget_usd is not None and total > self._total_budget_usd
            ):
                raise LLMError(
                    LLMErrorCode.BUDGET_EXCEEDED, "live run budget exhausted", provider=provider
                )
            self._reserved_usd[request.run_id] = per_run
            self._reserved_total = total

    def _account(self, request: ModelRequest, model: str, response: ModelResponse) -> ModelResponse:
        prompt, completion = response.prompt_tokens, response.completion_tokens
        if (
            prompt is None
            or completion is None
            or not 0 <= prompt <= self._registry.get(model).max_context_tokens
            or not 0 <= completion <= request.max_output_tokens
        ):
            raise LLMError(
                LLMErrorCode.INVALID_RESPONSE,
                "provider usage is missing or exceeds the reserved token bounds",
                provider=response.provider,
            )
        cost = self._cost(model, prompt, completion)
        with self._budget_lock:
            self._spent_usd[request.run_id] = self._spent_usd.get(request.run_id, Decimal(0)) + cost
        return response.model_copy(update={"estimated_cost_usd": float(cost)})

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
