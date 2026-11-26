"""Provider-independent model contracts (spec section 5.1, FR-009)."""

from enum import StrEnum
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

LLMMode = Literal["mock", "replay", "hosted_free", "live_paid"]


class Capability(StrEnum):
    TOOL_CALLING = "tool_calling"
    STRUCTURED_OUTPUT = "structured_output"
    STREAMING = "streaming"
    USAGE_REPORTING = "usage_reporting"


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Message(_Frozen):
    role: Literal["system", "user", "assistant", "tool"]
    content: str
    tool_call_id: str | None = None


class ToolDefinition(_Frozen):
    name: str = Field(pattern=r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")
    description: str
    parameters: dict[str, object]


class ResponseSchema(_Frozen):
    """A named JSON Schema the response must satisfy."""

    name: str = Field(pattern=r"^[A-Za-z_][A-Za-z0-9_-]{0,63}$")
    json_schema: dict[str, object]


class ModelRequest(_Frozen):
    run_id: str = Field(min_length=1)
    messages: list[Message] = Field(min_length=1)
    tools: list[ToolDefinition] = Field(default_factory=list)
    response_schema: ResponseSchema | None = None
    required_capabilities: frozenset[Capability] = frozenset()
    max_output_tokens: int = Field(default=1024, ge=1)
    timeout_seconds: int = Field(default=30, ge=1, le=300)

    def needed_capabilities(self) -> frozenset[Capability]:
        needed = set(self.required_capabilities)
        if self.tools:
            needed.add(Capability.TOOL_CALLING)
        if self.response_schema is not None:
            needed.add(Capability.STRUCTURED_OUTPUT)
        return frozenset(needed)


class ToolCall(_Frozen):
    id: str
    name: str
    arguments: dict[str, object]


class ModelResponse(_Frozen):
    text: str | None
    structured: dict[str, object] | None = None
    tool_calls: list[ToolCall] = Field(default_factory=list)
    provider: str
    model: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    elapsed_ms: int = Field(ge=0)
    estimated_cost_usd: float | None = None


class ModelCapabilities(_Frozen):
    provider: str
    model: str
    capabilities: frozenset[Capability]
    max_context_tokens: int = Field(ge=1)


class LLMProvider(Protocol):
    """Port implemented by every model adapter. Adapters raise only ``LLMError``."""

    name: str

    def capabilities(self, model: str) -> ModelCapabilities: ...

    async def generate(self, request: ModelRequest, model: str) -> ModelResponse: ...
