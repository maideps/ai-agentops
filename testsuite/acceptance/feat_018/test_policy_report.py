"""Verify policy guidance in actual report requests, without hosted model calls."""

import asyncio
import json

import psycopg
import pytest

from agentops_agents import workflow
from agentops_agents.state import AgentRunState, Evidence, RunLimits, RunStatus, TaskRequest
from agentops_agents.workflow import Orchestration, RunDependencies, run_task
from agentops_core.llm import LLMGateway, ModelRequest
from agentops_evals.benchmark import specialist_turns
from agentops_llm.mock import MOCK_MODEL
from agentops_retrieval.embedding import HashingEmbedder
from agentops_tools.gateway import ToolGateway
from testsuite.acceptance.feat_004.harness import LLM_FIXTURES, SAMPLE_TASK
from testsuite.acceptance.feat_014.test_quarter_context import RecordingProvider

GUIDANCE = "Document evidence available in this context:"


def _no_database() -> psycopg.Connection:
    raise AssertionError("this report-node test must not open a database")


def _report_request(
    evidence: list[Evidence], *, max_context_tokens: int = 1500
) -> tuple[ModelRequest, AgentRunState, workflow._Run]:
    run_id = "feat018-report"
    provider = RecordingProvider(
        run_id, [{"text": json.dumps({"summary": "No supported findings.", "findings": []})}]
    )
    deps = RunDependencies(
        gateway=LLMGateway(provider, MOCK_MODEL),
        llm_provider="mock",
        llm_model=MOCK_MODEL,
        connect=_no_database,
        embedder=HashingEmbedder(),
        limits=RunLimits(max_context_tokens=max_context_tokens),
    )
    run = workflow._Run(deps, None, 0.0)
    state: AgentRunState = {
        "run_id": run_id,
        "task_text": "Explain the decline and the applicable company policy.",
        "evidence": [item.model_dump() for item in evidence],
    }
    update = asyncio.run(run.synthesize_report(state))
    state["context"] = update["context"]
    return provider.requests[0], state, run


def _evidence(evidence_id: str, kind: str, text: str) -> Evidence:
    return Evidence.model_validate(
        {"id": evidence_id, "kind": kind, "source_uri": "synthetic:test", "text": text}
    )


def test_guidance_lists_only_document_passages_that_fit_the_context() -> None:
    sales = _evidence("sales:decline", "sales", "Revenue declined.")
    policy = _evidence("doc:policy#0", "document", "Returns require proof.")
    dropped = _evidence("doc:dropped#0", "document", "Long passage. " * 100)
    issue = _evidence("issue:1", "issue", "Customer asked about returns.")
    request, state, _ = _report_request([sales, policy, dropped, issue], max_context_tokens=25)
    system = request.messages[0].content
    assert f"{GUIDANCE} [doc:policy#0]" in system
    assert "doc:dropped#0" not in system
    assert "sales:decline" not in system and "issue:1" not in system
    assert "When these passages support relevant company policy guidance" in system
    assert "cite the supporting document passage in the same finding" in system
    assert "Do not invent a policy claim or add an unsupported citation" in system
    assert state["context"]["dropped_evidence_ids"] == ["doc:dropped#0"]
    assert "[doc:policy#0] Returns require proof." in request.messages[1].content
    assert "Long passage." not in request.messages[1].content


@pytest.mark.parametrize("with_dropped_document", [False, True])
def test_no_included_document_keeps_the_existing_report_prompt(
    with_dropped_document: bool,
) -> None:
    evidence = [_evidence("sales:decline", "sales", "Revenue declined.")]
    if with_dropped_document:
        evidence.append(_evidence("doc:dropped#0", "document", "Long passage. " * 100))
    request, _, _ = _report_request(evidence, max_context_tokens=10)
    assert request.messages[0].content == workflow.REPORT_PROMPT
    assert GUIDANCE not in request.messages[0].content


@pytest.mark.parametrize("citation", ["doc:not-provided#0", "doc:dropped#0"])
def test_document_guidance_does_not_authorize_a_missing_context_citation(
    citation: str,
) -> None:
    _, state, run = _report_request(
        [
            _evidence("doc:policy#0", "document", "Returns require proof."),
            _evidence("doc:dropped#0", "document", "Long passage. " * 100),
        ],
        max_context_tokens=10,
    )
    state["draft_report"] = {
        "summary": "Unsupported policy claim.",
        "findings": [{"claim": "No proof needed.", "citations": [citation]}],
    }
    result = asyncio.run(run.output_policy(state))
    assert result["status"] == RunStatus.ABSTAINED.value
    assert result["abstain_reason"] == "NO_SUPPORTED_FINDINGS"
    assert result["policy_decisions"][-1]["decision"] == "deny"


@pytest.mark.parametrize("orchestration", ["single", "specialists"])
def test_policy_template_changes_are_part_of_prompt_provenance(
    orchestration: Orchestration, monkeypatch: pytest.MonkeyPatch
) -> None:
    before = workflow.prompt_version(orchestration)
    monkeypatch.setattr(workflow, "POLICY_REPORT_PROMPT", "Changed policy guidance: {evidence_ids}")
    assert workflow.prompt_version(orchestration) != before


@pytest.mark.integration
@pytest.mark.parametrize("orchestration", ["single", "specialists"])
def test_both_workflows_send_policy_guidance_after_real_retrieval(
    seeded_db: str, analytics_dsn: str, app_dsn: str, orchestration: Orchestration
) -> None:
    sample = json.loads((LLM_FIXTURES / "run-sample-q3-declines.json").read_text(encoding="utf-8"))
    turns = sample["turns"]
    if orchestration == "specialists":
        turns = specialist_turns(turns)
    run_id = f"feat018-{orchestration}"
    provider = RecordingProvider(run_id, turns)
    deps = RunDependencies(
        gateway=LLMGateway(provider, MOCK_MODEL),
        llm_provider="mock",
        llm_model=MOCK_MODEL,
        connect=lambda: psycopg.connect(analytics_dsn),
        embedder=HashingEmbedder(),
        tool_gateway=ToolGateway(
            connect=lambda: psycopg.connect(app_dsn), embedder=HashingEmbedder()
        ),
        orchestration=orchestration,
    )
    detail = asyncio.run(
        run_task(
            TaskRequest(
                run_id=run_id,
                tenant_id="demo-a",
                user_id="user-a-analyst",
                task_text=SAMPLE_TASK,
            ),
            deps,
        )
    )
    assert detail.status is RunStatus.COMPLETED
    report_request = provider.requests[-1]
    included = set(detail.context.included_evidence_ids)
    documents = [item.id for item in detail.evidence if item.kind == "document"]
    assert documents
    system = report_request.messages[0].content
    assert GUIDANCE in system
    for evidence_id in documents:
        assert (f"[{evidence_id}]" in system) == (evidence_id in included)
    assert detail.report is not None
    assert any(
        citation in documents
        for finding in detail.report.findings
        for citation in finding.citations
    )
