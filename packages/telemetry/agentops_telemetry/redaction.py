"""Redaction of secrets and personal data from telemetry (NFR-004).

Spans should carry identifiers, counts and codes only; this is the safety net for anything
that slips through (an exception message, a URL, a token in an argument).
"""

import re
from collections.abc import Mapping, Sequence

REDACTED = "[REDACTED]"

_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # Credentials inside URLs: scheme://user:password@host -> scheme://user:[REDACTED]@host
    (re.compile(r"(\b[a-zA-Z][a-zA-Z0-9+.-]*://[^:/\s@]+:)[^@\s/]+(@)"), rf"\1{REDACTED}\2"),
    # Provider and Langfuse keys (same families as arch-104) and test canaries.
    (re.compile(r"\bsk-(?:ant-|proj-)?[A-Za-z0-9_-]{20,}"), REDACTED),
    (re.compile(r"\bAIza[0-9A-Za-z_-]{35}"), REDACTED),
    (re.compile(r"\bgsk_[A-Za-z0-9]{20,}"), REDACTED),
    (re.compile(r"\b[ps]k-lf-[0-9a-f-]{20,}"), REDACTED),
    (re.compile(r"\bCANARY-[A-Z]+-[A-Za-z0-9]+"), REDACTED),
    # Bearer and basic auth tokens.
    (re.compile(r"(?i)\b(Bearer|Basic)\s+[A-Za-z0-9._~+/=-]+"), rf"\1 {REDACTED}"),
    # password=..., secret: ..., api_key="..."
    (
        re.compile(r"(?i)\b(password|passwd|secret|api[_-]?key|token)(\s*[=:]\s*)\S+"),
        rf"\1\2{REDACTED}",
    ),
    # E-mail addresses.
    (re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"), "[EMAIL]"),
]


def redact(value: str) -> str:
    for pattern, replacement in _PATTERNS:
        value = pattern.sub(replacement, value)
    return value


def redact_value(value: object) -> object:
    if isinstance(value, str):
        return redact(value)
    if isinstance(value, bytes):
        return REDACTED
    if isinstance(value, Mapping):
        return {str(k): redact_value(v) for k, v in value.items()}
    if isinstance(value, Sequence):
        return tuple(redact_value(item) for item in value)
    return value


def redact_attributes(attributes: Mapping[str, object] | None) -> dict[str, object]:
    return {key: redact_value(value) for key, value in (attributes or {}).items()}
