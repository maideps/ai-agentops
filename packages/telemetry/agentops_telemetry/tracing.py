"""OpenTelemetry tracing with redaction before export and optional Langfuse (OTLP) export.

Span names follow the spec taxonomy: http.request, agent.run, agent.node, llm.generate,
rag.retrieve, tool.authorize, tool.execute, tool.reconcile, approval.wait, policy.evaluate,
eval.case. Attributes carry ids, counts and codes, never prompt or document text.
"""

import base64
import os
import secrets
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from typing import Any

from opentelemetry import context as otel_context
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import Event, ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    SimpleSpanProcessor,
    SpanExporter,
    SpanExportResult,
)
from opentelemetry.trace import NonRecordingSpan, SpanContext, Status, TraceFlags

from agentops_telemetry.redaction import redact, redact_attributes

TRACER_NAME = "agentops"
LANGFUSE_DEFAULT_HOST = "https://cloud.langfuse.com"


class RedactingSpanExporter(SpanExporter):
    """Wraps an exporter and scrubs attributes, events and status before anything leaves."""

    def __init__(self, inner: SpanExporter) -> None:
        self._inner = inner

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        return self._inner.export([_redacted(s) for s in spans])

    def shutdown(self) -> None:
        self._inner.shutdown()

    def force_flush(self, timeout_millis: int = 30_000) -> bool:
        return self._inner.force_flush(timeout_millis)


def _redacted(item: ReadableSpan) -> ReadableSpan:
    status = item.status
    if status.description:
        status = Status(status.status_code, redact(status.description))
    return ReadableSpan(
        name=item.name,
        context=item.context,
        parent=item.parent,
        resource=item.resource,
        attributes=redact_attributes(item.attributes),  # type: ignore[arg-type]
        events=[
            Event(e.name, redact_attributes(e.attributes), e.timestamp)  # type: ignore[arg-type]
            for e in item.events
        ],
        links=item.links,
        kind=item.kind,
        status=status,
        start_time=item.start_time,
        end_time=item.end_time,
        instrumentation_scope=item.instrumentation_scope,
    )


def _langfuse_exporter(environ: Mapping[str, str]) -> SpanExporter:
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

    public, secret = environ.get("LANGFUSE_PUBLIC_KEY"), environ.get("LANGFUSE_SECRET_KEY")
    if not public or not secret:
        msg = "LANGFUSE_ENABLED needs LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY"
        raise ValueError(msg)
    host = environ.get("LANGFUSE_HOST", LANGFUSE_DEFAULT_HOST).rstrip("/")
    token = base64.b64encode(f"{public}:{secret}".encode()).decode()
    return OTLPSpanExporter(
        endpoint=f"{host}/api/public/otel/v1/traces",
        headers={"Authorization": f"Basic {token}"},
    )


def configure_tracing(
    *,
    service_name: str,
    exporter: SpanExporter | None = None,
    langfuse_enabled: bool = False,
    environ: Mapping[str, str] | None = None,
    set_global: bool = True,
) -> TracerProvider:
    """A tracer provider whose exporters all sit behind ``RedactingSpanExporter``.

    ``exporter`` is exported synchronously (tests, local debugging); Langfuse is batched and
    used only when ``langfuse_enabled`` is set and its keys are present.
    """
    provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
    if exporter is not None:
        provider.add_span_processor(SimpleSpanProcessor(RedactingSpanExporter(exporter)))
    if langfuse_enabled:
        langfuse = _langfuse_exporter(environ if environ is not None else os.environ)
        provider.add_span_processor(BatchSpanProcessor(RedactingSpanExporter(langfuse)))
    if set_global:
        trace.set_tracer_provider(provider)
    return provider


@contextmanager
def span(
    name: str,
    attributes: Mapping[str, Any] | None = None,
    *,
    trace_id: str | None = None,
    provider: TracerProvider | None = None,
) -> Iterator[trace.Span]:
    """Start a span; with ``trace_id`` and no active span, the span joins that trace.

    Attributes are redacted when set, and again on export.
    """
    tracer = (provider or trace.get_tracer_provider()).get_tracer(TRACER_NAME)
    token = None
    if trace_id is not None and not trace.get_current_span().get_span_context().is_valid:
        parent = SpanContext(
            trace_id=int(trace_id, 16),
            span_id=secrets.randbits(64) or 1,
            is_remote=True,
            trace_flags=TraceFlags(TraceFlags.SAMPLED),
        )
        token = otel_context.attach(trace.set_span_in_context(NonRecordingSpan(parent)))
    try:
        safe = {k: v for k, v in redact_attributes(attributes).items() if v is not None}
        with tracer.start_as_current_span(name, attributes=safe) as current:  # type: ignore[arg-type]
            yield current
    finally:
        if token is not None:
            otel_context.detach(token)
