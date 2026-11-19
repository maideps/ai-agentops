"""LLM gateway: capability check before execution, structured-output validation after."""

import json

from jsonschema import Draft202012Validator

from agentops_core.llm.contracts import LLMProvider, ModelRequest, ModelResponse, ResponseSchema
from agentops_core.llm.errors import LLMError, LLMErrorCode


class LLMGateway:
    def __init__(self, provider: LLMProvider, model: str) -> None:
        self._provider = provider
        self._model = model

    async def generate(self, request: ModelRequest) -> ModelResponse:
        self._check_capabilities(request)
        response = await self._provider.generate(request, self._model)
        if request.response_schema is None:
            return response
        structured = _validated_structured(request.response_schema, response)
        return response.model_copy(update={"structured": structured})

    def _check_capabilities(self, request: ModelRequest) -> None:
        available = self._provider.capabilities(self._model).capabilities
        missing = sorted(request.needed_capabilities() - available)
        if missing:
            raise LLMError(
                LLMErrorCode.MODEL_CAPABILITY_UNSUPPORTED,
                f"model {self._model!r} lacks: {', '.join(missing)}",
                provider=self._provider.name,
            )


def _validated_structured(schema: ResponseSchema, response: ModelResponse) -> dict[str, object]:
    data: object = response.structured
    if data is None:
        try:
            data = json.loads(response.text or "")
        except json.JSONDecodeError:
            raise LLMError(
                LLMErrorCode.INVALID_RESPONSE,
                f"response for {schema.name!r} is not JSON",
                provider=response.provider,
            ) from None
    error = next(iter(Draft202012Validator(schema.json_schema).iter_errors(data)), None)
    if error is not None or not isinstance(data, dict):
        where = "/".join(str(part) for part in error.absolute_path) if error else ""
        raise LLMError(
            LLMErrorCode.INVALID_RESPONSE,
            f"response violates schema {schema.name!r} at '/{where}'",
            provider=response.provider,
        )
    return data
