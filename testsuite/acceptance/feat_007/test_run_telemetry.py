"""feat-007 (NFR-002, NFR-004, FR-003): a run's spans follow the spec taxonomy, share the run's
trace id, carry no secret, and every tool read now passes the gateway's role check."""

from typing import Any

import pytest

from agentops_agents.state import RunStatus
from testsuite.acceptance.feat_004.harness import FIXED_TRACE_ID, run

pytestmark = pytest.mark.integration

CANARY_TASK = (
    "Analyze quarterly sales, identify the three largest declines from 2026-Q2 to 2026-Q3. "
    "My password=CANARY-SECRET-0110 and my email is ana.analyst@example.com."
)


def test_sample_run_spans_follow_the_taxonomy_and_share_the_trace_id(
    seeded_db: str, analytics_dsn: str, span_exporter: Any
) -> None:
    span_exporter.clear()

    detail, _ = run(analytics_dsn, task_text=CANARY_TASK)

    spans = span_exporter.get_finished_spans()
    names = {s.name for s in spans}
    assert {
        "agent.run",
        "agent.node",
        "llm.generate",
        "policy.evaluate",
        "tool.authorize",
        "tool.execute",
        "rag.retrieve",
    } <= names
    assert {format(s.context.trace_id, "032x") for s in spans} == {FIXED_TRACE_ID}
    assert detail.trace_id == FIXED_TRACE_ID
    for item in spans:
        if item.name.startswith("agent."):
            assert item.attributes is not None
            assert item.attributes.get("agentops.run_id") == detail.run_id
    exported = "\n".join(s.to_json() for s in spans)
    assert "CANARY-SECRET" not in exported
    assert "example.com" not in exported


def test_viewer_cannot_read_sales_through_the_workflow(seeded_db: str, analytics_dsn: str) -> None:
    """Regression test from eval case access-viewer-sales (see D-011)."""
    detail, _ = run(analytics_dsn, user_id="user-a-viewer")

    denied = {(d.subject, d.reason_code) for d in detail.policy_decisions if d.decision == "deny"}
    assert ("tool_call:call-1:get_sales_summary", "PERMISSION_DENIED") in denied
    assert detail.analytics is None
    assert not any(item.kind == "sales" for item in detail.evidence)
    assert detail.status is RunStatus.ABSTAINED
