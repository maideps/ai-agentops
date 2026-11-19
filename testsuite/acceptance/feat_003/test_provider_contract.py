"""feat-003 (FR-009): one contract suite for every LLMProvider adapter.

The LiteLLM adapter runs with a stubbed completion function, so nothing reaches a provider.
"""

import asyncio
from collections.abc import Callable

import pytest

from agentops_core.llm import (
    Capability,
    LLMError,
    LLMErrorCode,
    LLMGateway,
    LLMProvider,
    Message,
    ModelRequest,
    ModelResponse,
    ResponseSchema,
    ToolDefinition,
)
from testsuite.acceptance.feat_003.providers import (
    MODEL,
    Script,
    scripted_litellm_provider,
    scripted_mock_provider,
)

ProviderFactory = Callable[[Script], LLMProvider]
FACTORIES: dict[str, ProviderFactory] = {
    "mock": scripted_mock_provider,
    "litellm-stub": scripted_litellm_provider,
}

SUMMARY_SCHEMA = ResponseSchema(
    name="sales_summary",
    json_schema={
        "type": "object",
        "properties": {"total": {"type": "number"}, "region": {"type": "string"}},
        "required": ["total", "region"],
        "additionalProperties": False,
    },
)
LOOKUP_TOOL = ToolDefinition(
    name="get_sales_summary",
    description="Read-only quarterly sales summary",
    parameters={
        "type": "object",
        "properties": {"quarter": {"type": "string"}},
        "required": ["quarter"],
    },
)


def _request(**overrides: object) -> ModelRequest:
    fields: dict[str, object] = {
        "run_id": "run-1",
        "messages": [Message(role="user", content="Summarize Q3 sales")],
    }
    fields.update(overrides)
    return ModelRequest.model_validate(fields)


def _generate(provider: LLMProvider, request: ModelRequest) -> ModelResponse:
    return asyncio.run(LLMGateway(provider, MODEL).generate(request))


@pytest.fixture(params=sorted(FACTORIES))
def make_provider(request: pytest.FixtureRequest) -> ProviderFactory:
    return FACTORIES[request.param]


def test_text_response_is_normalized(make_provider: ProviderFactory) -> None:
    provider = make_provider([{"text": "Q3 sales fell 12%."}])

    response = _generate(provider, _request())

    assert response.text == "Q3 sales fell 12%."
    assert response.structured is None
    assert response.tool_calls == []
    assert response.model == MODEL
    assert response.prompt_tokens is not None and response.prompt_tokens > 0
    assert response.completion_tokens is not None and response.completion_tokens > 0
    assert response.elapsed_ms >= 0


def test_tool_call_is_normalized(make_provider: ProviderFactory) -> None:
    provider = make_provider(
        [
            {
                "tool_calls": [
                    {"id": "call-1", "name": "get_sales_summary", "arguments": {"quarter": "Q3"}}
                ]
            }
        ]
    )

    response = _generate(provider, _request(tools=[LOOKUP_TOOL]))

    assert len(response.tool_calls) == 1
    call = response.tool_calls[0]
    assert (call.id, call.name, call.arguments) == (
        "call-1",
        "get_sales_summary",
        {"quarter": "Q3"},
    )


def test_structured_output_is_parsed_and_validated(make_provider: ProviderFactory) -> None:
    provider = make_provider([{"text": '{"total": 1250.5, "region": "EMEA"}'}])

    response = _generate(provider, _request(response_schema=SUMMARY_SCHEMA))

    assert response.structured == {"total": 1250.5, "region": "EMEA"}


def test_structured_output_violating_the_schema_is_rejected(make_provider: ProviderFactory) -> None:
    provider = make_provider([{"text": '{"total": "lots"}'}])

    with pytest.raises(LLMError) as raised:
        _generate(provider, _request(response_schema=SUMMARY_SCHEMA))

    assert raised.value.code is LLMErrorCode.INVALID_RESPONSE


def test_structured_output_that_is_not_json_is_rejected(make_provider: ProviderFactory) -> None:
    provider = make_provider([{"text": "total is 1250"}])

    with pytest.raises(LLMError) as raised:
        _generate(provider, _request(response_schema=SUMMARY_SCHEMA))

    assert raised.value.code is LLMErrorCode.INVALID_RESPONSE


@pytest.mark.parametrize(
    "code",
    [
        LLMErrorCode.RATE_LIMITED,
        LLMErrorCode.AUTH_FAILED,
        LLMErrorCode.TIMEOUT,
        LLMErrorCode.PROVIDER_UNAVAILABLE,
        LLMErrorCode.CAPABILITY_UNSUPPORTED,
        LLMErrorCode.BUDGET_EXCEEDED,
    ],
)
def test_provider_errors_are_normalized(make_provider: ProviderFactory, code: LLMErrorCode) -> None:
    provider = make_provider([{"error": code.value}])

    with pytest.raises(LLMError) as raised:
        _generate(provider, _request())

    assert raised.value.code is code
    assert raised.value.retryable is (code in {LLMErrorCode.RATE_LIMITED, LLMErrorCode.TIMEOUT})


def test_capabilities_are_reported(make_provider: ProviderFactory) -> None:
    capabilities = make_provider([]).capabilities(MODEL)

    assert capabilities.model == MODEL
    assert Capability.TOOL_CALLING in capabilities.capabilities
    assert Capability.STRUCTURED_OUTPUT in capabilities.capabilities
