"""feat-012 (D-016): the hosted Gemini Flash-Lite model is allowlisted and selected only with
opt-in; a per-run LLM_BUDGET_USD cap aborts with BUDGET_EXCEEDED before the spend crosses it;
the provider key never appears in errors. No network: completion is stubbed."""

import asyncio
from types import SimpleNamespace

import pytest
from openai import APIError

from agentops_core.llm import Capability, LLMError, LLMErrorCode, Message, ModelRequest
from agentops_llm.hosted import GEMINI_FLASH_LITE, hosted_registry
from agentops_llm.litellm_provider import LiteLLMProvider
from agentops_llm.mock import MockLLMProvider
from agentops_llm.selection import select_provider
from agentops_llm.testing import stub_completion

CANARY = "CANARY-SECRET-0007"


def _request(**overrides: object) -> ModelRequest:
    fields: dict[str, object] = {
        "run_id": "r",
        "messages": [Message(role="user", content="hello world")],
        "max_output_tokens": 10,
    }
    fields.update(overrides)
    return ModelRequest.model_validate(fields)


def _fake_raw(prompt_tokens: int, completion_tokens: int, text: str = "ok") -> object:
    """A completion response with attribute-style usage, like LiteLLM returns."""
    usage = SimpleNamespace(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens)
    message = SimpleNamespace(content=text, tool_calls=None)
    return SimpleNamespace(choices=[SimpleNamespace(message=message)], usage=usage)


def test_hosted_registry_lists_gemini_flash_lite() -> None:
    capabilities = hosted_registry().get(GEMINI_FLASH_LITE)

    assert capabilities.provider == "gemini"
    assert capabilities.model == GEMINI_FLASH_LITE
    assert Capability.TOOL_CALLING in capabilities.capabilities
    assert Capability.STRUCTURED_OUTPUT in capabilities.capabilities
    assert Capability.USAGE_REPORTING in capabilities.capabilities
    assert capabilities.max_context_tokens == 1_048_576


def test_hosted_registry_refuses_unlisted_models() -> None:
    with pytest.raises(LLMError) as raised:
        hosted_registry().get("openai/gpt-4o-mini")

    assert raised.value.code is LLMErrorCode.MODEL_CAPABILITY_UNSUPPORTED


def test_live_modes_still_require_opt_in() -> None:
    with pytest.raises(LLMError) as raised:
        select_provider("hosted_free", enable_live_llm=False, live_factory=MockLLMProvider)

    assert raised.value.code is LLMErrorCode.PROVIDER_UNAVAILABLE


def test_budget_aborts_before_the_first_call_when_the_estimate_exceeds() -> None:
    calls: list[str] = []

    async def completion(**kwargs: object) -> object:
        calls.append("called")
        return _fake_raw(prompt_tokens=1, completion_tokens=1)

    provider = LiteLLMProvider(
        registry=hosted_registry(),
        completion=completion,
        budget_usd=0.5,
        cost_estimator=lambda model, prompt, completion_tokens: 1.0,
    )

    with pytest.raises(LLMError) as raised:
        asyncio.run(provider.generate(_request(), GEMINI_FLASH_LITE))

    assert raised.value.code is LLMErrorCode.BUDGET_EXCEEDED
    assert calls == []


def test_budget_tracks_cumulative_spend_across_calls() -> None:
    calls = 0

    async def completion(**kwargs: object) -> object:
        nonlocal calls
        calls += 1
        return _fake_raw(prompt_tokens=10, completion_tokens=10)

    provider = LiteLLMProvider(
        registry=hosted_registry(),
        completion=completion,
        budget_usd=1.0,
        cost_estimator=lambda model, prompt, completion_tokens: 0.6,
    )

    first = asyncio.run(provider.generate(_request(), GEMINI_FLASH_LITE))
    assert first.estimated_cost_usd == 0.6

    with pytest.raises(LLMError) as raised:
        asyncio.run(provider.generate(_request(), GEMINI_FLASH_LITE))

    assert raised.value.code is LLMErrorCode.BUDGET_EXCEEDED
    assert calls == 1


def test_api_key_never_appears_in_errors() -> None:
    stub = stub_completion([{"error": "AUTH_FAILED"}])
    received: list[object] = []

    async def completion(**kwargs: object) -> object:
        received.append(kwargs["api_key"])
        try:
            return await stub(**kwargs)
        except APIError as exc:
            exc.message = f"provider echoed {CANARY}"
            exc.args = (exc.message,)
            raise

    provider = LiteLLMProvider(
        registry=hosted_registry(),
        completion=completion,
        api_key=CANARY,
    )

    with pytest.raises(LLMError) as raised:
        asyncio.run(provider.generate(_request(), GEMINI_FLASH_LITE))

    assert raised.value.code is LLMErrorCode.AUTH_FAILED
    assert received == [CANARY]
    assert CANARY not in str(raised.value)
    assert CANARY not in raised.value.message


def test_budget_reserves_the_entire_input_window_not_a_word_estimate() -> None:
    bounds: list[tuple[int, int]] = []

    def cost(model: str, prompt: int, completion: int) -> float:
        bounds.append((prompt, completion))
        return prompt * 1e-7 + completion * 4e-7

    provider = LiteLLMProvider(
        registry=hosted_registry(),
        completion=stub_completion([{"text": "not called"}]),
        budget_usd=0.001,
        cost_estimator=cost,
    )
    with pytest.raises(LLMError) as raised:
        asyncio.run(provider.generate(_request(), GEMINI_FLASH_LITE))

    assert raised.value.code is LLMErrorCode.BUDGET_EXCEEDED
    assert bounds == [(1_048_576, 10)]


def test_concurrent_calls_reserve_before_awaiting_the_provider() -> None:
    calls = 0

    async def completion(**kwargs: object) -> object:
        nonlocal calls
        calls += 1
        await asyncio.sleep(0)
        return _fake_raw(1, 1)

    provider = LiteLLMProvider(
        registry=hosted_registry(),
        completion=completion,
        budget_usd=1.0,
        cost_estimator=lambda model, prompt, completion: 0.6,
    )

    async def go() -> list[object]:
        return list(
            await asyncio.gather(
                provider.generate(_request(), GEMINI_FLASH_LITE),
                provider.generate(_request(), GEMINI_FLASH_LITE),
                return_exceptions=True,
            )
        )

    results = asyncio.run(go())
    assert calls == 1
    errors = [r for r in results if isinstance(r, LLMError)]
    assert len(errors) == 1
    assert errors[0].code is LLMErrorCode.BUDGET_EXCEEDED


def test_uncertain_failed_calls_do_not_refund_the_reservation() -> None:
    provider = LiteLLMProvider(
        registry=hosted_registry(),
        completion=stub_completion([{"error": "TIMEOUT"}, {"text": "not called"}]),
        budget_usd=1.0,
        cost_estimator=lambda model, prompt, completion: 0.6,
    )
    with pytest.raises(LLMError) as first:
        asyncio.run(provider.generate(_request(), GEMINI_FLASH_LITE))
    assert first.value.code is LLMErrorCode.TIMEOUT

    with pytest.raises(LLMError) as second:
        asyncio.run(provider.generate(_request(), GEMINI_FLASH_LITE))
    assert second.value.code is LLMErrorCode.BUDGET_EXCEEDED


@pytest.mark.parametrize("cost", [float("nan"), float("inf"), -1.0])
def test_unbounded_prices_fail_closed_before_calling(cost: float) -> None:
    provider = LiteLLMProvider(
        registry=hosted_registry(),
        completion=stub_completion([{"text": "not called"}]),
        budget_usd=1.0,
        cost_estimator=lambda model, prompt, completion: cost,
    )
    with pytest.raises(LLMError) as raised:
        asyncio.run(provider.generate(_request(), GEMINI_FLASH_LITE))
    assert raised.value.code is LLMErrorCode.BUDGET_EXCEEDED


def test_gemini_key_is_loaded_without_enabling_live_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from agentops_api.runs import _live_provider
    from agentops_api.settings import Settings
    from agentops_llm import hosted

    captured: list[tuple[str | None, float]] = []

    def factory(api_key: str | None, budget_usd: float) -> MockLLMProvider:
        captured.append((api_key, budget_usd))
        return MockLLMProvider()

    monkeypatch.setenv("GEMINI_API_KEY", CANARY)
    monkeypatch.setenv("LLM_BUDGET_USD", "0.25")
    monkeypatch.setattr(hosted, "hosted_provider", factory)
    settings = Settings()
    assert settings.llm_mode == "mock"
    assert not settings.enable_live_llm
    assert CANARY not in repr(settings)
    _live_provider(settings)
    assert captured == [(CANARY, 0.25)]


def test_batch_budget_covers_different_run_ids() -> None:
    provider = LiteLLMProvider(
        registry=hosted_registry(),
        completion=stub_completion([{"text": "ok"}, {"text": "not called"}]),
        budget_usd=1.0,
        total_budget_usd=1.0,
        cost_estimator=lambda model, prompt, completion: 0.6,
    )
    asyncio.run(provider.generate(_request(run_id="one"), GEMINI_FLASH_LITE))
    with pytest.raises(LLMError) as raised:
        asyncio.run(provider.generate(_request(run_id="two"), GEMINI_FLASH_LITE))
    assert raised.value.code is LLMErrorCode.BUDGET_EXCEEDED
    assert provider.reserved_usd("one") == 0.6
    assert provider.reserved_usd("two") == 0.0


def test_missing_usage_is_not_reported_as_zero_cost() -> None:
    async def completion(**kwargs: object) -> object:
        raw = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="ok", tool_calls=[]))]
        )
        return raw

    provider = LiteLLMProvider(
        registry=hosted_registry(),
        completion=completion,
        budget_usd=1.0,
        cost_estimator=lambda model, prompt, completion: 0.6,
    )
    with pytest.raises(LLMError) as raised:
        asyncio.run(provider.generate(_request(), GEMINI_FLASH_LITE))
    assert raised.value.code is LLMErrorCode.INVALID_RESPONSE
    assert provider.reserved_usd("r") == 0.6


def test_budgeted_calls_cannot_hide_retries() -> None:
    with pytest.raises(LLMError) as raised:
        LiteLLMProvider(registry=hosted_registry(), budget_usd=1.0, num_retries=1)
    assert raised.value.code is LLMErrorCode.INVALID_REQUEST


def test_default_price_map_reports_real_usage_cost_offline() -> None:
    async def completion(**kwargs: object) -> object:
        return _fake_raw(100, 10)

    provider = LiteLLMProvider(registry=hosted_registry(), completion=completion, budget_usd=0.2)
    response = asyncio.run(provider.generate(_request(), GEMINI_FLASH_LITE))
    assert response.estimated_cost_usd == pytest.approx(0.000014)
    assert provider.spent_usd("r") == pytest.approx(0.000014)
    assert provider.reserved_usd("r") == pytest.approx(0.1048616)


def test_live_provider_refuses_a_missing_key() -> None:
    from agentops_api.problems import ProblemError
    from agentops_api.runs import _live_provider
    from agentops_api.settings import Settings

    with pytest.raises(ProblemError) as raised:
        _live_provider(Settings())
    assert raised.value.code == "AUTH_FAILED"
