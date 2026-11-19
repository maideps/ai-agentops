"""feat-003 (FR-010, NFR-009): capability checks run before any provider call; live providers
are selected only with explicit opt-in; mock mode needs no network.
"""

import asyncio
from pathlib import Path

import pytest

from agentops_core.llm import (
    Capability,
    CapabilityRegistry,
    LLMError,
    LLMErrorCode,
    LLMGateway,
    Message,
    ModelCapabilities,
    ModelRequest,
    ModelResponse,
    ResponseSchema,
    ToolDefinition,
)
from agentops_llm.mock import MockLLMProvider
from agentops_llm.selection import select_provider

TEXT_ONLY = ModelCapabilities(
    provider="stub",
    model="stub/text-only",
    capabilities=frozenset({Capability.USAGE_REPORTING}),
    max_context_tokens=4_096,
)


class SpyProvider:
    """Records calls; must never be reached when a capability is missing."""

    name = "spy"

    def __init__(self) -> None:
        self.calls = 0

    def capabilities(self, model: str) -> ModelCapabilities:
        return CapabilityRegistry([TEXT_ONLY]).get(model)

    async def generate(self, request: ModelRequest, model: str) -> ModelResponse:
        self.calls += 1
        raise AssertionError("provider must not be called")


def _request(**overrides: object) -> ModelRequest:
    fields: dict[str, object] = {"run_id": "r", "messages": [Message(role="user", content="hi")]}
    fields.update(overrides)
    return ModelRequest.model_validate(fields)


@pytest.mark.parametrize(
    ("overrides", "missing"),
    [
        (
            {"tools": [ToolDefinition(name="t", description="d", parameters={"type": "object"})]},
            Capability.TOOL_CALLING,
        ),
        (
            {"response_schema": ResponseSchema(name="s", json_schema={"type": "object"})},
            Capability.STRUCTURED_OUTPUT,
        ),
        ({"required_capabilities": {Capability.STREAMING}}, Capability.STREAMING),
    ],
)
def test_missing_capability_fails_before_the_provider_is_called(
    overrides: dict[str, object], missing: Capability
) -> None:
    spy = SpyProvider()

    with pytest.raises(LLMError) as raised:
        asyncio.run(LLMGateway(spy, "stub/text-only").generate(_request(**overrides)))

    assert raised.value.code is LLMErrorCode.MODEL_CAPABILITY_UNSUPPORTED
    assert missing.value in raised.value.message
    assert spy.calls == 0


def test_unknown_model_is_unsupported() -> None:
    with pytest.raises(LLMError) as raised:
        CapabilityRegistry([TEXT_ONLY]).get("stub/never-registered")

    assert raised.value.code is LLMErrorCode.MODEL_CAPABILITY_UNSUPPORTED


def test_mock_mode_selects_the_mock_and_never_builds_a_live_provider() -> None:
    def live_factory() -> MockLLMProvider:
        raise AssertionError("live provider must not be built in mock mode")

    provider = select_provider("mock", enable_live_llm=True, live_factory=live_factory)

    assert isinstance(provider, MockLLMProvider)


@pytest.mark.parametrize("mode", ["hosted_free", "live_paid"])
def test_live_modes_without_opt_in_are_refused(mode: str) -> None:
    with pytest.raises(LLMError) as raised:
        select_provider(mode, enable_live_llm=False, live_factory=MockLLMProvider)  # type: ignore[arg-type]

    assert raised.value.code is LLMErrorCode.PROVIDER_UNAVAILABLE


def test_live_mode_with_opt_in_uses_the_live_factory() -> None:
    sentinel = MockLLMProvider()

    assert (
        select_provider("hosted_free", enable_live_llm=True, live_factory=lambda: sentinel)
        is sentinel
    )


def test_replay_mode_refuses_every_model_call() -> None:
    provider = select_provider("replay", enable_live_llm=False, live_factory=MockLLMProvider)

    with pytest.raises(LLMError) as raised:
        asyncio.run(provider.generate(_request(), "mock-deterministic-v1"))

    assert raised.value.code is LLMErrorCode.PROVIDER_UNAVAILABLE


def test_mock_loads_fixture_scripts_from_disk(tmp_path: Path) -> None:
    (tmp_path / "q3.json").write_text(
        '{"run_id": "fixture-run", "turns": [{"text": "from fixture"}]}', encoding="utf-8"
    )
    provider = MockLLMProvider.from_directory(tmp_path)
    request = _request(run_id="fixture-run")

    response = asyncio.run(LLMGateway(provider, "mock-deterministic-v1").generate(request))

    assert response.text == "from fixture"
    assert response.provider == "mock"
    assert response.estimated_cost_usd == 0.0


def test_mock_is_deterministic_and_fails_clearly_when_unscripted() -> None:
    provider = MockLLMProvider()

    with pytest.raises(LLMError) as raised:
        asyncio.run(provider.generate(_request(run_id="no-script"), "mock-deterministic-v1"))

    assert raised.value.code is LLMErrorCode.PROVIDER_UNAVAILABLE
    assert "no-script" in raised.value.message


def test_real_litellm_call_is_blocked_at_the_provider_host(
    blocked_network_attempts: list[str],
) -> None:
    """The default LiteLLM completion path really tries the provider and the guard stops it.

    OpenAI is used because LiteLLM's Gemini and Groq paths first download a tokenizer
    (D-005), so they never reach their provider host in an offline test.
    """
    from agentops_llm.litellm_provider import LiteLLMProvider

    model = "openai/gpt-4o-mini"
    registry = CapabilityRegistry(
        [
            ModelCapabilities(
                provider="openai", model=model, capabilities=frozenset(), max_context_tokens=8_192
            )
        ]
    )
    provider = LiteLLMProvider(registry=registry, api_key="CANARY-SECRET-0006")

    with pytest.raises(LLMError) as raised:
        asyncio.run(LLMGateway(provider, model).generate(_request(timeout_seconds=5)))

    assert raised.value.code is LLMErrorCode.PROVIDER_UNAVAILABLE
    assert "CANARY-SECRET" not in str(raised.value)
    assert blocked_network_attempts, "the call should have been stopped by the network guard"
    assert set(blocked_network_attempts) == {"api.openai.com"}
