"""Typed model errors (spec 5.2, FR-010). Messages never carry provider text or secrets."""

from enum import StrEnum


class LLMErrorCode(StrEnum):
    # Pre-execution check against the capability registry (FR-010).
    MODEL_CAPABILITY_UNSUPPORTED = "MODEL_CAPABILITY_UNSUPPORTED"
    # Provider-reported errors (spec 5.2).
    RATE_LIMITED = "RATE_LIMITED"
    AUTH_FAILED = "AUTH_FAILED"
    TIMEOUT = "TIMEOUT"
    CAPABILITY_UNSUPPORTED = "CAPABILITY_UNSUPPORTED"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    BUDGET_EXCEEDED = "BUDGET_EXCEEDED"
    # Additions (D-005): rejected request, unusable response.
    INVALID_REQUEST = "INVALID_REQUEST"
    INVALID_RESPONSE = "INVALID_RESPONSE"
    # feat-015: the reply stopped at max_output_tokens, so structured output is incomplete.
    OUTPUT_TRUNCATED = "OUTPUT_TRUNCATED"
    # feat-021: a rate limit on a per-day quota; waiting seconds cannot help, so never retried.
    QUOTA_EXHAUSTED = "QUOTA_EXHAUSTED"


_RETRYABLE = frozenset({LLMErrorCode.RATE_LIMITED, LLMErrorCode.TIMEOUT})


class LLMError(Exception):
    def __init__(
        self,
        code: LLMErrorCode,
        message: str,
        *,
        provider: str | None = None,
        retry_after_seconds: float | None = None,
    ) -> None:
        super().__init__(f"{code.value}: {message}")
        self.code = code
        self.message = message
        self.provider = provider
        self.retryable = code in _RETRYABLE
        self.retry_after_seconds = retry_after_seconds
