"""feat-023: a run states which sources the user's role kept from it.

The viewer's live run of access-01 completed from company documents after the sales tool was
denied, and nothing in the result said the sales data was missing. The workflow now records
each tool the gateway denied with PERMISSION_DENIED as an evidence gap, tells the report step,
and live scoring accepts a completed answer only when the gap is on record.
"""

import asyncio
import json
from pathlib import Path
from typing import Any, cast

import psycopg
import pytest

from agentops_agents import workflow
from agentops_agents.state import (
    AgentRunState,
    Evidence,
    EvidenceGap,
    RunDetail,
    RunStatus,
    TaskRequest,
)
from agentops_agents.workflow import RunDependencies, run_task
from agentops_core.llm import LLMGateway
from agentops_evals.corpus import Expect, LiveExpect, load_corpus
from agentops_evals.runner import score_live
from agentops_llm.mock import MOCK_MODEL
from agentops_retrieval.embedding import HashingEmbedder
from agentops_tools.gateway import CallContext, GatewayDenied, ToolGateway
from testsuite.acceptance.feat_004.harness import APP_DSN
from testsuite.acceptance.feat_014.test_quarter_context import RecordingProvider

SAMPLE = Path("fixtures/replays/run-sample-q3-declines.json")
SALES_GAP = EvidenceGap(tool="get_sales_summary", source="sales data")
GAP_TEXT = "These sources were not available to this user: sales data."
TASK = "Analyze quarterly sales from 2026-Q2 to 2026-Q3 and prepare a cited executive summary."


def _no_database() -> psycopg.Connection:
    raise AssertionError("this test must not open a database")


def _deps(provider: RecordingProvider, tool_gateway: object | None = None) -> RunDependencies:
    return RunDependencies(
        gateway=LLMGateway(provider, MOCK_MODEL),
        llm_provider="mock",
        llm_model=MOCK_MODEL,
        connect=_no_database,
        embedder=HashingEmbedder(),
        tool_gateway=cast(ToolGateway | None, tool_gateway),
    )


class DenyingGateway:
    """Denies sales for the role and one call's arguments; documents succeed."""

    def invoke(self, ctx: CallContext, name: str, arguments: dict[str, object]) -> dict[str, Any]:
        if name == "get_sales_summary":
            raise GatewayDenied("PERMISSION_DENIED")
        if arguments.get("query") == "bad":
            raise GatewayDenied("INVALID_ARGUMENTS")
        doc = {"id": "doc:a#0", "kind": "document", "source_uri": "synthetic:t", "text": "Text."}
        return {"evidence": [doc]}


def _call(call_id: str, name: str, **arguments: object) -> dict[str, object]:
    return {"id": call_id, "name": name, "arguments": arguments}


def test_only_permission_denials_become_gaps_once_per_tool() -> None:
    run = workflow._Run(_deps(RecordingProvider("r", []), DenyingGateway()), None, 0.0)
    state: AgentRunState = {
        "run_id": "r",
        "tenant_id": "demo-a",
        "user_id": "user-a-viewer",
        "authorized_tool_calls": [
            _call("c1", "get_sales_summary", from_quarter="2026-Q2", to_quarter="2026-Q3"),
            _call("c2", "get_sales_summary", from_quarter="2026-Q1", to_quarter="2026-Q2"),
            _call("c3", "search_approved_documents", query="bad", k=2),
            _call("c4", "search_approved_documents", query="press kit", k=2),
        ],
    }
    update = asyncio.run(run.execute_tools(state))
    assert update["evidence_gaps"] == [SALES_GAP.model_dump()]
    denied = [d["reason_code"] for d in update["policy_decisions"]]
    assert denied == ["PERMISSION_DENIED", "PERMISSION_DENIED", "INVALID_ARGUMENTS"]
    assert "status" not in update  # document evidence remains, so the run continues


def _report_system_prompt(gaps: list[EvidenceGap]) -> str:
    provider = RecordingProvider(
        "r", [{"text": json.dumps({"summary": "Nothing supported.", "findings": []})}]
    )
    run = workflow._Run(_deps(provider), None, 0.0)
    sales = {"id": "sales:x", "kind": "sales", "source_uri": "synthetic:t", "text": "Down."}
    state: AgentRunState = {
        "run_id": "r",
        "task_text": TASK,
        "evidence": [Evidence.model_validate(sales).model_dump()],
        "evidence_gaps": [gap.model_dump() for gap in gaps],
    }
    asyncio.run(run.synthesize_report(state))
    return provider.requests[0].messages[0].content


def test_the_report_step_is_told_which_sources_were_unavailable() -> None:
    system = _report_system_prompt([SALES_GAP])
    assert GAP_TEXT in system
    assert "say in the summary that the answer does not include them" in system
    assert _report_system_prompt([]) == workflow.REPORT_PROMPT


@pytest.mark.parametrize("orchestration", ["single", "specialists"])
def test_the_gap_prompt_is_part_of_the_prompt_version(
    monkeypatch: pytest.MonkeyPatch, orchestration: workflow.Orchestration
) -> None:
    original = workflow.prompt_version(orchestration)
    monkeypatch.setattr(workflow, "GAP_REPORT_PROMPT", "changed")
    assert workflow.prompt_version(orchestration) != original


# --- scoring -------------------------------------------------------------------------------


@pytest.fixture
def sample() -> RunDetail:
    return RunDetail.model_validate(json.loads(SAMPLE.read_text(encoding="utf-8")))


def test_live_completion_needs_the_gap_on_record(sample: RunDetail) -> None:
    live = LiveExpect(outcomes=["abstained", "completed"], discloses_gaps=["get_sales_summary"])
    assert score_live(live, Expect(), sample, 0, sample.trace_id) == [
        "completed without disclosing gaps ['get_sales_summary']"
    ]
    disclosed = sample.model_copy(update={"evidence_gaps": [SALES_GAP]})
    assert score_live(live, Expect(), disclosed, 0, sample.trace_id) == []
    abstained = sample.model_copy(update={"status": RunStatus.ABSTAINED, "report": None})
    assert score_live(live, Expect(), abstained, 0, sample.trace_id) == []


def test_access_01_accepts_abstaining_or_answering_with_the_gap_stated() -> None:
    corpus = load_corpus()
    assert corpus.dataset_version == "evals-v1.3.0"
    case = next(c for c in corpus.cases if c.id == "access-01")
    assert case.expect.evidence_gaps == ["get_sales_summary"]
    assert case.expect.forbidden_evidence_prefixes == ["sales:"]
    assert case.live is not None
    assert case.live.outcomes == ["abstained", "completed"]
    assert case.live.discloses_gaps == ["get_sales_summary"]
    others = [c.id for c in corpus.cases if c.live and c.live.discloses_gaps]
    assert others == ["access-01"]


# --- whole runs against the seeded database ------------------------------------------------


def _run(
    analytics_dsn: str,
    run_id: str,
    turns: list[dict[str, Any]],
    orchestration: workflow.Orchestration = "single",
    user_id: str = "user-a-analyst",
) -> tuple[RunDetail, RecordingProvider]:
    provider = RecordingProvider(run_id, turns)
    deps = RunDependencies(
        gateway=LLMGateway(provider, MOCK_MODEL),
        llm_provider=provider.name,
        llm_model=MOCK_MODEL,
        connect=lambda: psycopg.connect(analytics_dsn),
        embedder=HashingEmbedder(),
        tool_gateway=ToolGateway(
            connect=lambda: psycopg.connect(APP_DSN), embedder=HashingEmbedder()
        ),
        orchestration=orchestration,
    )
    request = TaskRequest(run_id=run_id, tenant_id="demo-a", user_id=user_id, task_text=TASK)
    return asyncio.run(run_task(request, deps)), provider


TOOL_TURN = {
    "tool_calls": [
        _call("call-1", "get_sales_summary", from_quarter="2026-Q2", to_quarter="2026-Q3", top_n=3),
        _call("call-2", "search_approved_documents", query="press kit", k=2),
    ]
}
DOCUMENT_REPORT = {
    "text": json.dumps(
        {
            "summary": "Company context only; sales data was not available.",
            "findings": [{"claim": "Acme sells outdoor gear.", "citations": ["doc-a-press-kit#0"]}],
        }
    )
}


@pytest.mark.integration
@pytest.mark.parametrize("orchestration", ["single", "specialists"])
def test_a_viewer_completes_from_documents_with_the_sales_gap_recorded(
    seeded_db: str, analytics_dsn: str, orchestration: workflow.Orchestration
) -> None:
    sales_call, documents_call = TOOL_TURN["tool_calls"]
    turns: list[dict[str, Any]] = (
        [TOOL_TURN, DOCUMENT_REPORT]
        if orchestration == "single"
        else [{"tool_calls": [documents_call]}, {"tool_calls": [sales_call]}, DOCUMENT_REPORT]
    )
    detail, provider = _run(
        analytics_dsn, f"feat023-viewer-{orchestration}", turns, orchestration, "user-a-viewer"
    )
    assert detail.status is RunStatus.COMPLETED
    assert detail.evidence_gaps == [SALES_GAP]
    assert detail.analytics is None
    assert not [e.id for e in detail.evidence if e.id.startswith("sales:")]
    assert GAP_TEXT in provider.requests[-1].messages[0].content


@pytest.mark.integration
def test_an_analyst_with_sales_access_has_no_gap(seeded_db: str, analytics_dsn: str) -> None:
    detail, provider = _run(analytics_dsn, "feat023-analyst", [TOOL_TURN, DOCUMENT_REPORT])
    assert detail.status is RunStatus.COMPLETED
    assert detail.evidence_gaps == []
    assert detail.analytics is not None
    assert "not available to this user" not in provider.requests[-1].messages[0].content
