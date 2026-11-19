"""Provider selection: mock by default; a live provider only with explicit opt-in (NFR-009)."""

from collections.abc import Callable

from agentops_core.llm import (
    LLMError,
    LLMErrorCode,
    LLMMode,
    LLMProvider,
    ModelCapabilities,
    ModelRequest,
    ModelResponse,
)
from agentops_llm.mock import MockLLMProvider


class ReplayProvider:
    """Replay mode serves recorded runs; every model call is refused."""

    name = "replay"

    def _refuse(self) -> LLMError:
        return LLMError(
            LLMErrorCode.PROVIDER_UNAVAILABLE,
            "model calls are disabled in replay mode",
            provider=self.name,
        )

    def capabilities(self, model: str) -> ModelCapabilities:
        raise self._refuse()

    async def generate(self, request: ModelRequest, model: str) -> ModelResponse:
        raise self._refuse()


def select_provider(
    mode: LLMMode,
    *,
    enable_live_llm: bool,
    live_factory: Callable[[], LLMProvider],
    mock_factory: Callable[[], LLMProvider] = MockLLMProvider,
) -> LLMProvider:
    """Pick the provider for ``mode``. ``live_factory`` is called only for an opted-in live mode."""
    if mode == "mock":
        return mock_factory()
    if mode == "replay":
        return ReplayProvider()
    if not enable_live_llm:
        raise LLMError(
            LLMErrorCode.PROVIDER_UNAVAILABLE,
            f"LLM_MODE={mode} requires ENABLE_LIVE_LLM=true",
        )
    return live_factory()
