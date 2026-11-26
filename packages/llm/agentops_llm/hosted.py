"""Hosted model registry entries (deny by default; a model is unusable unless listed here).

The Gemini Flash-Lite entry mirrors the bundled LiteLLM model map
(``gemini/gemini-3.5-flash-lite``: max input 1_048_576, max output 65_536 tokens;
input 3e-7 USD/token, output 2.5e-6 USD/token). Provider selection stays independent of
the adapter: this module imports only the ``agentops_core`` port, never LiteLLM.
"""

from typing import TYPE_CHECKING

from agentops_core.llm import (
    Capability,
    CapabilityRegistry,
    LLMError,
    LLMErrorCode,
    ModelCapabilities,
)

if TYPE_CHECKING:
    from agentops_llm.litellm_provider import LiteLLMProvider

GEMINI_FLASH_LITE = "gemini/gemini-3.5-flash-lite"

GEMINI_FLASH_LITE_CAPABILITIES = ModelCapabilities(
    provider="gemini",
    model=GEMINI_FLASH_LITE,
    capabilities=frozenset(
        {Capability.TOOL_CALLING, Capability.STRUCTURED_OUTPUT, Capability.USAGE_REPORTING}
    ),
    max_context_tokens=1_048_576,
)


def hosted_registry() -> CapabilityRegistry:
    """The allowlist of hosted models this deployment may call."""
    return CapabilityRegistry([GEMINI_FLASH_LITE_CAPABILITIES])


def hosted_provider(
    api_key: str | None,
    budget_usd: float,
    *,
    total_budget_usd: float | None = None,
    min_call_interval: float = 0.0,
) -> "LiteLLMProvider":
    from agentops_llm.litellm_provider import LiteLLMProvider

    if not api_key or not api_key.strip():
        raise LLMError(LLMErrorCode.AUTH_FAILED, "GEMINI_API_KEY is required for live calls")
    return LiteLLMProvider(
        registry=hosted_registry(),
        api_key=api_key,
        budget_usd=budget_usd,
        total_budget_usd=total_budget_usd,
        min_call_interval=min_call_interval,
    )
