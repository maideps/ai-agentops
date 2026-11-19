"""feat-007 (NFR-002, NFR-004): spans are redacted before export, and a run's spans share the
run's trace id."""

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import Status, StatusCode

from agentops_telemetry.redaction import redact
from agentops_telemetry.tracing import RedactingSpanExporter, configure_tracing, span

CANARIES = [
    "CANARY-SECRET-0101",
    "sk-proj-ABCDEFGHIJKLMNOPQRSTUVWXYZ012345",  # fake; arch-104 allows this file
    "postgresql://agentops:CANARY-SECRET-0102@db.internal:5432/agentops",
    "Bearer eyJhbGciOiJIUzI1NiJ9.CANARYTOKEN0103",
    "ana.analyst@example.com",
]


def _emit(provider: TracerProvider) -> None:
    tracer = provider.get_tracer("test")
    with tracer.start_as_current_span("tool.execute") as current:
        current.set_attribute("agentops.note", " | ".join(CANARIES))
        current.set_attribute("agentops.list", CANARIES)
        current.add_event("exception", {"exception.message": f"failed for {CANARIES[2]}"})
        current.set_status(Status(StatusCode.ERROR, f"boom {CANARIES[0]}"))


def _exported_text(exporter: InMemorySpanExporter) -> str:
    return "\n".join(item.to_json() for item in exporter.get_finished_spans())


def test_redaction_removes_secrets_tokens_credentials_and_emails() -> None:
    for value in CANARIES:
        assert redact(value) != value
    assert redact("postgresql://u:pw@host/db") == "postgresql://u:[REDACTED]@host/db"
    assert redact("revenue fell 4,000.00 in EMEA") == "revenue fell 4,000.00 in EMEA"


def test_exporter_redacts_attributes_events_and_status() -> None:
    raw, redacted = InMemorySpanExporter(), InMemorySpanExporter()
    unprotected, protected = TracerProvider(), TracerProvider()
    unprotected.add_span_processor(SimpleSpanProcessor(raw))
    protected.add_span_processor(SimpleSpanProcessor(RedactingSpanExporter(redacted)))

    _emit(unprotected)
    _emit(protected)

    assert "CANARY-SECRET-0101" in _exported_text(raw)  # the layer is what removes it
    text = _exported_text(redacted)
    for secret in ("CANARY-SECRET", "sk-proj-", "CANARYTOKEN", "example.com"):
        assert secret not in text
    assert "[REDACTED]" in text


def test_span_helper_joins_the_given_trace_id() -> None:
    exporter = InMemorySpanExporter()
    provider = configure_tracing(service_name="test", exporter=exporter, set_global=False)
    trace_id = "0123456789abcdef0123456789abcdef"

    with (
        span("agent.run", {"agentops.run_id": "r1"}, trace_id=trace_id, provider=provider),
        span("agent.node", {"agentops.node": "plan"}, provider=provider),
    ):
        pass

    spans = exporter.get_finished_spans()
    assert {s.name for s in spans} == {"agent.run", "agent.node"}
    assert {format(s.context.trace_id, "032x") for s in spans} == {trace_id}


def test_langfuse_export_needs_explicit_opt_in_and_keys() -> None:
    provider = configure_tracing(service_name="test", langfuse_enabled=False, set_global=False)
    assert provider is not None

    try:
        configure_tracing(service_name="test", langfuse_enabled=True, environ={}, set_global=False)
    except ValueError as error:
        assert "LANGFUSE_PUBLIC_KEY" in str(error)
    else:
        raise AssertionError("Langfuse export without keys must be refused")


def test_configured_provider_always_exports_through_redaction() -> None:
    exporter = InMemorySpanExporter()
    provider = configure_tracing(service_name="test", exporter=exporter, set_global=False)

    _emit(provider)

    assert "CANARY-SECRET" not in _exported_text(exporter)


def test_api_refuses_to_start_with_langfuse_enabled_but_no_keys() -> None:
    from agentops_api.app import create_app
    from agentops_api.settings import Settings

    try:
        create_app(Settings(langfuse_enabled=True))
    except ValueError as error:
        assert "LANGFUSE_PUBLIC_KEY" in str(error)
    else:
        raise AssertionError("the API must not start half-configured")
