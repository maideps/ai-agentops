"""Deterministic mock provider: scripted turns per run id, no network, zero cost."""

import json
from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from agentops_core.llm import (
    Capability,
    CapabilityRegistry,
    LLMError,
    LLMErrorCode,
    ModelCapabilities,
    ModelRequest,
    ModelResponse,
    ToolCall,
)

MOCK_MODEL = "mock-deterministic-v1"
MOCK_CAPABILITIES = ModelCapabilities(
    provider="mock",
    model=MOCK_MODEL,
    capabilities=frozenset(Capability),
    max_context_tokens=128_000,
)


def approx_tokens(text: str) -> int:
    """Deterministic stand-in for a tokenizer: whitespace-separated words, at least one."""
    return max(1, len(text.split()))


class MockTurn(BaseModel):
    """One scripted model reply: text, tool calls, or a normalized error."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    text: str | None = None
    tool_calls: list[ToolCall] = Field(default_factory=list)
    error: LLMErrorCode | None = None

    @model_validator(mode="after")
    def _exactly_one_kind(self) -> Self:
        kinds = [self.text is not None, bool(self.tool_calls), self.error is not None]
        if sum(kinds) != 1:
            msg = "a mock turn needs exactly one of text, tool_calls or error"
            raise ValueError(msg)
        return self

    def completion_tokens(self) -> int:
        if self.text is not None:
            return approx_tokens(self.text)
        return sum(approx_tokens(json.dumps(call.arguments)) for call in self.tool_calls)


class MockScript(BaseModel):
    """The replies for one run, returned in order."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: str
    turns: list[MockTurn]


class MockLLMProvider:
    name = "mock"

    def __init__(
        self,
        scripts: Iterable[MockScript] = (),
        capabilities: ModelCapabilities = MOCK_CAPABILITIES,
    ) -> None:
        self._scripts = {script.run_id: script for script in scripts}
        self._registry = CapabilityRegistry([capabilities])
        self._calls: defaultdict[str, int] = defaultdict(int)

    @classmethod
    def from_directory(cls, directory: Path) -> Self:
        """Load every ``*.json`` script in ``directory`` (sorted, for determinism)."""
        scripts = [
            MockScript.model_validate_json(path.read_text(encoding="utf-8"))
            for path in sorted(directory.glob("*.json"))
        ]
        return cls(scripts)

    def capabilities(self, model: str) -> ModelCapabilities:
        return self._registry.get(model)

    async def generate(self, request: ModelRequest, model: str) -> ModelResponse:
        script = self._scripts.get(request.run_id)
        if script is None:
            raise LLMError(
                LLMErrorCode.PROVIDER_UNAVAILABLE,
                f"no mock script for run {request.run_id!r}",
                provider=self.name,
            )
        index = self._calls[request.run_id]
        self._calls[request.run_id] += 1
        if index >= len(script.turns):
            raise LLMError(
                LLMErrorCode.PROVIDER_UNAVAILABLE,
                f"mock script for run {request.run_id!r} has no turn {index + 1}",
                provider=self.name,
            )
        turn = script.turns[index]
        if turn.error is not None:
            raise LLMError(turn.error, "scripted mock error", provider=self.name)
        return ModelResponse(
            text=turn.text,
            tool_calls=turn.tool_calls,
            provider=self.name,
            model=model,
            prompt_tokens=sum(approx_tokens(message.content) for message in request.messages),
            completion_tokens=turn.completion_tokens(),
            elapsed_ms=0,
            estimated_cost_usd=0.0,
        )
