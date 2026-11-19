"""feat-004 (FR-002, FR-003, FR-012, NFR-002, NFR-005): the sample task end to end in mock mode."""

import json
import os
from decimal import Decimal

import pytest

from agentops_agents.state import RunDetail, RunStatus
from testsuite.acceptance.feat_004.harness import FIXED_TRACE_ID, REPLAYS, SAMPLE_RUN_ID, run

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def sample(seeded_db: str, analytics_dsn: str) -> RunDetail:
    detail, provider = run(analytics_dsn)
    assert provider.calls == 2
    return detail


def test_sample_task_completes_with_trace_and_bounded_calls(sample: RunDetail) -> None:
    assert sample.status is RunStatus.COMPLETED
    assert sample.run_id == SAMPLE_RUN_ID
    assert sample.trace_id == FIXED_TRACE_ID
    assert (sample.llm_calls, sample.tool_calls_executed) == (2, 2)
    assert sample.llm_provider == "mock"


def test_three_largest_declines_are_computed_by_the_sales_tool(sample: RunDetail) -> None:
    assert sample.analytics is not None
    declines = [
        (row.product_name, row.region, row.from_revenue, row.to_revenue, row.change)
        for row in sample.analytics.declines
    ]
    assert declines == [
        (
            "Trail Running Shoes",
            "EMEA",
            Decimal("10000.00"),
            Decimal("6000.00"),
            Decimal("-4000.00"),
        ),
        ("Rain Jacket", "NA", Decimal("9000.00"), Decimal("6000.00"), Decimal("-3000.00")),
        ("Camping Stove", "NA", Decimal("7000.00"), Decimal("5000.00"), Decimal("-2000.00")),
    ]
    assert (sample.analytics.total_from, sample.analytics.total_to) == (
        Decimal("56000.00"),
        Decimal("47500.00"),
    )


def test_every_reported_claim_cites_evidence_the_run_actually_used(sample: RunDetail) -> None:
    assert sample.report is not None
    used = set(sample.context.included_evidence_ids)
    assert len(sample.report.findings) == 3
    for finding in sample.report.findings:
        assert finding.citations
        assert set(finding.citations) <= used
    cited = {citation for finding in sample.report.findings for citation in finding.citations}
    assert "doc-a-returns-policy#1" in cited
    assert "doc-a-pricing-guidelines#1" in cited


def test_restricted_documents_never_reach_the_analysts_run(sample: RunDetail) -> None:
    evidence_ids = {item.id for item in sample.evidence}
    assert not any(item.startswith("doc-a-board-notes") for item in evidence_ids)
    assert not any(item.startswith("doc-b-") for item in evidence_ids)


def test_policy_rejections_are_recorded_in_the_run_detail(sample: RunDetail) -> None:
    denied = {
        (decision.subject, decision.reason_code)
        for decision in sample.policy_decisions
        if decision.decision == "deny"
    }
    assert ("tool_call:call-3:run_sql", "TOOL_NOT_ALLOWED") in denied
    assert ("tool_call:call-4:search_approved_documents", "INVALID_ARGUMENTS") in denied
    assert ("finding:3", "UNSUPPORTED_CITATION") in denied
    assert all(decision.policy_version for decision in sample.policy_decisions)


def test_run_reproduces_the_recorded_replay(sample: RunDetail) -> None:
    path = REPLAYS / f"{SAMPLE_RUN_ID}.json"
    actual = sample.model_dump(mode="json")
    if os.environ.get("AGENTOPS_UPDATE_REPLAYS") == "1":
        path.write_bytes((json.dumps(actual, indent=2, sort_keys=True) + "\n").encode())
    assert actual == json.loads(path.read_text(encoding="utf-8"))
