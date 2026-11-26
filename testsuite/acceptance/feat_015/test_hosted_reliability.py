"""feat-015 (FR-011, NFR-005, NFR-009): hosted calls survive transient failures within budget.

The feat-014 live run lost most report calls to HTTP 503 "high demand" and network outages,
and one diagnostic report stopped at the 500-token limit. No network: completions are stubs
from agentops_llm.testing (only packages/llm may import LiteLLM, arch-101).
"""

import asyncio
from typing import Any

import pytest

from agentops_agents.state import RunLimits
from agentops_api.settings import Settings
from agentops_core.llm import LLMError, LLMErrorCode, Message, ModelRequest
from agentops_llm.hosted import GEMINI_FLASH_LITE, hosted_registry
from agentops_llm.litellm_provider import LiteLLMProvider
from agentops_llm.testing import stub_outcomes

# Reservation per attempt at the default 1,024 output tokens: 1,048,576 * 3e-7 + 1,024 * 2.5e-6.
BOUND = 0.3171328
UNAVAILABLE = LLMErrorCode.PROVIDER_UNAVAILABLE.value  # stubbed as an HTTP 503


def _provider(
    outcomes: list[str], budget: float = 10.0
) -> tuple[LiteLLMProvider, list[int], list[float]]:
    completion, attempts = stub_outcomes(outcomes)
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
    provider, attempts, sleeps = _provider([UNAVAILABLE, "ok"])
    response = _generate(provider)
    assert response.text == "{}"
    assert len(attempts) == 2
    assert sleeps == [1.0]
    assert provider.retries("r") == 1
    assert provider.reserved_usd("r") == pytest.approx(2 * BOUND)


def test_three_503s_fail_after_exactly_three_attempts() -> None:
    provider, attempts, sleeps = _provider([UNAVAILABLE] * 3)
    with pytest.raises(LLMError) as raised:
        _generate(provider)
    assert raised.value.code is LLMErrorCode.PROVIDER_UNAVAILABLE
    assert len(attempts) == 3
    assert sleeps == [1.0, 2.0]
    assert provider.retries("r") == 2
    assert provider.reserved_usd("r") == pytest.approx(3 * BOUND)


def test_connection_errors_are_retried_but_timeouts_are_not() -> None:
    provider, attempts, _ = _provider(["CONNECTION", "ok"])
    _generate(provider)
    assert len(attempts) == 2

    provider, attempts, _ = _provider([LLMErrorCode.TIMEOUT.value, "ok"])
    with pytest.raises(LLMError) as raised:
        _generate(provider)
    assert raised.value.code is LLMErrorCode.TIMEOUT
    assert len(attempts) == 1


@pytest.mark.parametrize(
    "code",
    [LLMErrorCode.RATE_LIMITED, LLMErrorCode.INVALID_REQUEST, LLMErrorCode.AUTH_FAILED],
)
def test_non_transient_errors_are_attempted_once(code: LLMErrorCode) -> None:
    provider, attempts, sleeps = _provider([code.value, "ok"])
    with pytest.raises(LLMError) as raised:
        _generate(provider)
    assert raised.value.code is code
    assert (len(attempts), sleeps, provider.retries("r")) == (1, [], 0)


def test_a_retry_the_budget_cannot_cover_is_not_sent() -> None:
    provider, attempts, _ = _provider([UNAVAILABLE, "ok"], budget=1.5 * BOUND)
    with pytest.raises(LLMError) as raised:
        _generate(provider)
    assert raised.value.code is LLMErrorCode.PROVIDER_UNAVAILABLE
    assert len(attempts) == 1
    assert provider.retries("r") == 0
    assert provider.reserved_usd("r") == pytest.approx(BOUND)


def test_a_reply_cut_at_the_output_limit_is_truncated_and_still_costed() -> None:
    provider, _, _ = _provider(["length"])
    with pytest.raises(LLMError) as raised:
        _generate(provider)
    assert raised.value.code is LLMErrorCode.OUTPUT_TRUNCATED
    assert provider.spent_usd("r") > 0
