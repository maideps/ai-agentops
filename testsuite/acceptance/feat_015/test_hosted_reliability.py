"""feat-015 (FR-011, NFR-005, NFR-009): hosted calls survive transient failures within budget.

The feat-014 live run lost most report calls to HTTP 503 "high demand" and network outages,
and one diagnostic report stopped at the 500-token limit. No network: completions are stubs.
"""

import asyncio
from collections.abc import Callable
from typing import Any

import litellm
import pytest
from litellm import exceptions as llx

from agentops_agents.state import RunLimits
from agentops_api.settings import Settings
from agentops_core.llm import LLMError, LLMErrorCode, Message, ModelRequest
from agentops_llm.hosted import GEMINI_FLASH_LITE, hosted_registry
from agentops_llm.litellm_provider import LiteLLMProvider

# Reservation per attempt at the default 1,024 output tokens: 1,048,576 * 3e-7 + 1,024 * 2.5e-6.
BOUND = 0.3171328


def _ok(finish_reason: str = "stop") -> Any:
    return litellm.ModelResponse(
        id="ok",
        model=GEMINI_FLASH_LITE,
        choices=[
            {
                "index": 0,
                "finish_reason": finish_reason,
                "message": {"role": "assistant", "content": "{}"},
            }
        ],
        usage={"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120},
    )


def _unavailable() -> Exception:
    return llx.ServiceUnavailableError(message="high demand", llm_provider="gemini", model="m")


def _scripted(outcomes: list[Callable[[], Any]]) -> tuple[Callable[..., Any], list[int]]:
    attempts: list[int] = []

    async def completion(**kwargs: Any) -> Any:
        attempts.append(1)
        outcome = outcomes[len(attempts) - 1]()
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    return completion, attempts


def _provider(
    outcomes: list[Callable[[], Any]], budget: float = 10.0
) -> tuple[LiteLLMProvider, list[int], list[float]]:
    completion, attempts = _scripted(outcomes)
    sleeps: list[float] = []

    async def sleep(seconds: float) -> None:
        sleeps.append(seconds)

    provider = LiteLLMProvider(
        registry=hosted_registry(),
        completion=completion,
        budget_usd=budget,
        total_budget_usd=budget,
        sleep=sleep,
    )
    return provider, attempts, sleeps


def _generate(provider: LiteLLMProvider) -> Any:
    request = ModelRequest(run_id="r", messages=[Message(role="user", content="report")])
    return asyncio.run(provider.generate(request, GEMINI_FLASH_LITE))


def test_default_output_limit_fits_a_hosted_report() -> None:
    request = ModelRequest(run_id="r", messages=[Message(role="user", content="x")])
    assert request.max_output_tokens == 1024
    assert RunLimits().max_output_tokens == 1024
    assert Settings().max_output_tokens == 1024


def test_a_503_then_success_completes_with_one_reserved_retry() -> None:
    provider, attempts, sleeps = _provider([_unavailable, _ok])
    response = _generate(provider)
    assert response.text == "{}"
    assert len(attempts) == 2
    assert sleeps == [1.0]
    assert provider.retries("r") == 1
    assert provider.reserved_usd("r") == pytest.approx(2 * BOUND)


def test_three_503s_fail_after_exactly_three_attempts() -> None:
    provider, attempts, sleeps = _provider([_unavailable] * 3)
    with pytest.raises(LLMError) as raised:
        _generate(provider)
    assert raised.value.code is LLMErrorCode.PROVIDER_UNAVAILABLE
    assert len(attempts) == 3
    assert sleeps == [1.0, 2.0]
    assert provider.retries("r") == 2
    assert provider.reserved_usd("r") == pytest.approx(3 * BOUND)


def test_connection_errors_are_retried_but_timeouts_are_not() -> None:
    def dns() -> Exception:
        return llx.APIConnectionError(message="getaddrinfo failed", llm_provider="g", model="m")

    provider, attempts, _ = _provider([dns, _ok])
    _generate(provider)
    assert len(attempts) == 2

    def timeout() -> Exception:
        return llx.Timeout(message="slow", model="m", llm_provider="g")

    provider, attempts, _ = _provider([timeout, _ok])
    with pytest.raises(LLMError) as raised:
        _generate(provider)
    assert raised.value.code is LLMErrorCode.TIMEOUT
    assert len(attempts) == 1


@pytest.mark.parametrize(
    "error, code",
    [
        (lambda: llx.RateLimitError(message="429", llm_provider="g", model="m"), "RATE_LIMITED"),
        (
            lambda: llx.BadRequestError(message="400", model="m", llm_provider="g"),
            "INVALID_REQUEST",
        ),
        (
            lambda: llx.AuthenticationError(message="401", llm_provider="g", model="m"),
            "AUTH_FAILED",
        ),
    ],
)
def test_non_transient_errors_are_attempted_once(error: Callable[[], Any], code: str) -> None:
    provider, attempts, sleeps = _provider([error, _ok])
    with pytest.raises(LLMError) as raised:
        _generate(provider)
    assert raised.value.code.value == code
    assert (len(attempts), sleeps, provider.retries("r")) == (1, [], 0)


def test_a_retry_the_budget_cannot_cover_is_not_sent() -> None:
    provider, attempts, _ = _provider([_unavailable, _ok], budget=1.5 * BOUND)
    with pytest.raises(LLMError) as raised:
        _generate(provider)
    assert raised.value.code is LLMErrorCode.PROVIDER_UNAVAILABLE
    assert len(attempts) == 1
    assert provider.retries("r") == 0
    assert provider.reserved_usd("r") == pytest.approx(BOUND)


def test_a_reply_cut_at_the_output_limit_is_truncated_and_still_costed() -> None:
    provider, _, _ = _provider([lambda: _ok("length")])
    with pytest.raises(LLMError) as raised:
        _generate(provider)
    assert raised.value.code is LLMErrorCode.OUTPUT_TRUNCATED
    assert provider.spent_usd("r") > 0
