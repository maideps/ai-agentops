"""feat-019 (FR-011, NFR-009): live calls stay within provider rate limits.

In the feat-017 live run every corpus failure was a free-tier HTTP 429, which was never
retried. Calls can now be paced, and a 429 gets a bounded, budget-reserved retry. No network:
completions are stubs, and the clock and sleep are injected so nothing waits.
"""

import asyncio
from typing import Any

import pytest

from agentops_core.llm import LLMError, LLMErrorCode, Message, ModelRequest
from agentops_evals import __main__ as cli
from agentops_llm.hosted import GEMINI_FLASH_LITE, hosted_registry
from agentops_llm.litellm_provider import LiteLLMProvider
from agentops_llm.testing import stub_outcomes

BOUND = 0.3171328  # reservation per attempt at 1,024 output tokens
LIMITED = LLMErrorCode.RATE_LIMITED.value


def _provider(
    outcomes: list[str], *, budget: float = 10.0, interval: float = 0.0
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
        min_call_interval=interval,
        clock=lambda: 100.0,  # frozen: every wait comes from pacing or retry policy
    )
    return provider, attempts, sleeps


def _generate(provider: LiteLLMProvider, run_id: str = "r") -> Any:
    request = ModelRequest(run_id=run_id, messages=[Message(role="user", content="report")])
    return asyncio.run(provider.generate(request, GEMINI_FLASH_LITE))


def test_attempts_are_spaced_by_the_minimum_interval() -> None:
    provider, attempts, sleeps = _provider(["ok", "ok", "ok"], interval=4.0)
    for run_id in ("a", "b", "c"):
        _generate(provider, run_id)
    assert len(attempts) == 3
    assert sleeps == [4.0, 8.0]  # with a frozen clock, slots are 100, 104 and 108


def test_no_interval_means_no_waiting() -> None:
    provider, _, sleeps = _provider(["ok", "ok"])
    _generate(provider, "a")
    _generate(provider, "b")
    assert sleeps == []


def test_a_429_then_success_completes_after_one_reserved_retry() -> None:
    provider, attempts, sleeps = _provider([LIMITED, "ok"])
    assert _generate(provider).text == "{}"
    assert (len(attempts), sleeps, provider.retries("r")) == (2, [10.0], 1)
    assert provider.reserved_usd("r") == pytest.approx(2 * BOUND)


def test_retry_after_is_honored_up_to_sixty_seconds() -> None:
    provider, attempts, sleeps = _provider(["RATE_LIMITED@7", "ok"])
    _generate(provider)
    assert (len(attempts), sleeps) == (2, [7.0])

    provider, attempts, sleeps = _provider(["RATE_LIMITED@60", "ok"])
    _generate(provider)
    assert sleeps == [60.0]


def test_a_retry_after_beyond_sixty_seconds_is_not_waited_for() -> None:
    provider, attempts, sleeps = _provider(["RATE_LIMITED@61", "ok"])
    with pytest.raises(LLMError) as raised:
        _generate(provider)
    assert raised.value.code is LLMErrorCode.RATE_LIMITED
    assert (len(attempts), sleeps, provider.retries("r")) == (1, [], 0)


def test_three_429s_fail_after_three_attempts() -> None:
    provider, attempts, sleeps = _provider([LIMITED] * 3)
    with pytest.raises(LLMError) as raised:
        _generate(provider)
    assert raised.value.code is LLMErrorCode.RATE_LIMITED
    assert (len(attempts), sleeps, provider.retries("r")) == (3, [10.0, 30.0], 2)


def test_429_and_503_share_the_two_retry_limit() -> None:
    provider, attempts, sleeps = _provider(
        [LIMITED, LLMErrorCode.PROVIDER_UNAVAILABLE.value, LIMITED]
    )
    with pytest.raises(LLMError):
        _generate(provider)
    assert (len(attempts), sleeps) == (3, [10.0, 2.0])


def test_a_429_retry_the_budget_cannot_cover_is_not_sent() -> None:
    provider, attempts, _ = _provider([LIMITED, "ok"], budget=1.5 * BOUND)
    with pytest.raises(LLMError) as raised:
        _generate(provider)
    assert raised.value.code is LLMErrorCode.RATE_LIMITED
    assert (len(attempts), provider.retries("r")) == (1, 0)
    assert provider.reserved_usd("r") == pytest.approx(BOUND)


def test_timeouts_stay_single_attempt() -> None:
    provider, attempts, sleeps = _provider([LLMErrorCode.TIMEOUT.value, "ok"])
    with pytest.raises(LLMError):
        _generate(provider)
    assert (len(attempts), sleeps) == (1, [])


def test_negative_interval_is_refused() -> None:
    with pytest.raises(LLMError):
        LiteLLMProvider(registry=hosted_registry(), min_call_interval=-1.0)


def test_cli_passes_the_interval_and_guards_it(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    seen: list[float] = []

    def fake_live_provider(budget_usd: float, min_call_interval: float = 0.0) -> Any:
        seen.append(min_call_interval)
        raise LLMError(LLMErrorCode.AUTH_FAILED, "stop after recording the interval")

    monkeypatch.setattr(cli, "_live_provider", fake_live_provider)
    argv = ["benchmark", "--live", "--budget-usd", "5", "--min-call-interval", "4"]
    assert cli.main(argv) == 2
    assert seen == [4.0]
    for bad in (
        ["benchmark", "--live", "--budget-usd", "5", "--min-call-interval", "-1"],
        ["benchmark", "--min-call-interval", "4"],
    ):
        with pytest.raises(SystemExit):
            cli.main(bad)
    capsys.readouterr()
