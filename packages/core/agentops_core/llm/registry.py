"""Capability registry: a model is unsupported unless it is registered (deny by default)."""

from collections.abc import Iterable

from agentops_core.llm.contracts import ModelCapabilities
from agentops_core.llm.errors import LLMError, LLMErrorCode


class CapabilityRegistry:
    def __init__(self, entries: Iterable[ModelCapabilities] = ()) -> None:
        self._entries: dict[str, ModelCapabilities] = {}
        for entry in entries:
            if entry.model in self._entries:
                msg = f"model registered twice: {entry.model}"
                raise ValueError(msg)
            self._entries[entry.model] = entry

    def get(self, model: str) -> ModelCapabilities:
        entry = self._entries.get(model)
        if entry is None:
            raise LLMError(
                LLMErrorCode.MODEL_CAPABILITY_UNSUPPORTED,
                f"model {model!r} is not in the capability registry",
            )
        return entry
