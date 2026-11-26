"""Test double for LiteLLM's completion function: real LiteLLM objects, no network."""

import json
from typing import Any

import litellm
from litellm import exceptions as llx

from agentops_core.llm import LLMErrorCode
from agentops_llm.litellm_provider import CompletionFn
from agentops_llm.mock import MockTurn, approx_tokens


def _litellm_error(code: LLMErrorCode, model: str) -> Exception:
    text = f"stubbed {code.value}"
    match code:
        case LLMErrorCode.RATE_LIMITED:
            return llx.RateLimitError(message=text, llm_provider="stub", model=model)
        case LLMErrorCode.AUTH_FAILED:
            return llx.AuthenticationError(message=text, llm_provider="stub", model=model)
        case LLMErrorCode.TIMEOUT:
            return llx.Timeout(message=text, model=model, llm_provider="stub")
        case LLMErrorCode.PROVIDER_UNAVAILABLE:
            return llx.ServiceUnavailableError(message=text, llm_provider="stub", model=model)
        case LLMErrorCode.CAPABILITY_UNSUPPORTED:
            return llx.UnsupportedParamsError(message=text, llm_provider="stub", model=model)
        case LLMErrorCode.BUDGET_EXCEEDED:
            return llx.BudgetExceededError(current_cost=1.0, max_budget=0.5)
        case LLMErrorCode.INVALID_REQUEST:
            return llx.BadRequestError(message=text, model=model, llm_provider="stub")
        case _:
            msg = f"no LiteLLM exception for {code.value}"
            raise ValueError(msg)


def stub_completion(script: list[dict[str, Any]]) -> CompletionFn:
    """Return an async ``acompletion`` stand-in that replays ``script`` turn by turn."""
    turns = [MockTurn.model_validate(turn) for turn in script]
    position = 0

    async def completion(**kwargs: Any) -> Any:
        nonlocal position
        turn = turns[position]
        position += 1
        model = str(kwargs["model"])
        if turn.error is not None:
            raise _litellm_error(turn.error, model)
        message: dict[str, Any] = {"role": "assistant", "content": turn.text}
        if turn.tool_calls:
            message["tool_calls"] = [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {"name": call.name, "arguments": json.dumps(call.arguments)},
                }
                for call in turn.tool_calls
            ]
        prompt_tokens = sum(approx_tokens(str(m.get("content", ""))) for m in kwargs["messages"])
        completion_tokens = turn.completion_tokens()
        return litellm.ModelResponse(
            id=f"stub-{position}",
            model=model,
            choices=[{"index": 0, "finish_reason": "stop", "message": message}],
            usage={
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
            },
        )

    return completion


def stub_outcomes(outcomes: list[str]) -> tuple[CompletionFn, list[int]]:
    """An ``acompletion`` stand-in for retry tests (feat-015) and the list of its attempts.

    Each outcome is ``"ok"``, ``"length"`` (a reply cut at the output limit), ``"CONNECTION"``
    (a network failure such as a DNS error), ``"RATE_LIMITED@<seconds>"`` (a 429 carrying a
    Retry-After header, feat-019) or an ``LLMErrorCode`` value to raise.
    """
    attempts: list[int] = []

    async def completion(**kwargs: Any) -> Any:
        attempts.append(1)
        outcome = outcomes[len(attempts) - 1]
        model = str(kwargs["model"])
        if outcome == "CONNECTION":
            raise llx.APIConnectionError(message="stubbed outage", llm_provider="stub", model=model)
        if outcome.startswith("RATE_LIMITED@"):
            raise llx.RateLimitError(
                message="stubbed 429",
                llm_provider="stub",
                model=model,
                headers={"Retry-After": outcome.split("@", 1)[1]},
            )
        if outcome not in ("ok", "length"):
            raise _litellm_error(LLMErrorCode(outcome), model)
        return litellm.ModelResponse(
            id=f"stub-{len(attempts)}",
            model=model,
            choices=[
                {
                    "index": 0,
                    "finish_reason": "stop" if outcome == "ok" else "length",
                    "message": {"role": "assistant", "content": "{}"},
                }
            ],
            usage={"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120},
        )

    return completion, attempts
