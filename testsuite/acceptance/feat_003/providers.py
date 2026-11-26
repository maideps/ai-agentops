"""Scripted providers for the feat-003 contract suite.

A script is a list of turns: ``{"text": ...}``, ``{"tool_calls": [...]}`` or ``{"error": code}``.
The same script drives the mock provider and the LiteLLM adapter (through a stubbed completion
function that builds real LiteLLM response objects), so both must normalize identically.
"""

from typing import Any

from agentops_core.llm import Capability, CapabilityRegistry, ModelCapabilities
from agentops_llm.litellm_provider import LiteLLMProvider
from agentops_llm.mock import MockLLMProvider, MockScript
from agentops_llm.testing import stub_completion

MODEL = "stub/contract-model"
Script = list[dict[str, Any]]

_CAPABILITIES = ModelCapabilities(
    provider="stub",
    model=MODEL,
    capabilities=frozenset(
        {Capability.TOOL_CALLING, Capability.STRUCTURED_OUTPUT, Capability.USAGE_REPORTING}
    ),
    max_context_tokens=8_192,
)


def scripted_mock_provider(script: Script) -> MockLLMProvider:
    return MockLLMProvider(
        scripts=[MockScript.model_validate({"run_id": "run-1", "turns": script})],
        capabilities=_CAPABILITIES,
    )


def scripted_litellm_provider(script: Script) -> LiteLLMProvider:
    return LiteLLMProvider(
        registry=CapabilityRegistry([_CAPABILITIES]),
        completion=stub_completion(script),
        # One scripted turn is one reply, as for the mock; retry policy is feat-015's suite.
        transient_retries=0,
    )
