"""feat-017 (FR-012, NFR-006, NFR-007): live evaluation scores answers, not mock trajectories.

The feat-015 live run completed 22 of 42 workflows yet scored 11/50, because most expectations
describe the mock's scripted trajectory. Live expectations score the outcome; safety
invariants still apply. No network or database: runs are stubbed.
"""

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from agentops_agents.state import PolicyDecision, RunDetail, RunStatus, TaskRequest
from agentops_agents.workflow import RunDependencies
from agentops_core.llm import Message, ModelRequest
from agentops_evals import benchmark, runner
from agentops_evals.corpus import Case, Corpus, Expect, LiveExpect, load_corpus
from agentops_evals.runner import score_live
from agentops_evals.scenarios import Env
from agentops_llm.hosted import hosted_registry
from agentops_llm.litellm_provider import LiteLLMProvider
from agentops_llm.testing import stub_completion

SAMPLE = Path("fixtures/replays/run-sample-q3-declines.json")


@pytest.fixture
def sample() -> RunDetail:
    """A real recorded run: completed, declines 101/EMEA, 102/NA, 103/NA, three cited findings."""
    return RunDetail.model_validate(json.loads(SAMPLE.read_text(encoding="utf-8")))


def _live(**fields: Any) -> LiveExpect:
    return LiveExpect.model_validate({"outcomes": ["completed"], **fields})


def test_a_superset_of_expected_declines_passes(sample: RunDetail) -> None:
    # The task asked for the largest decline; reporting the top three is still correct.
    live = _live(declines_include=[[101, "EMEA"]], min_findings=1)
    assert score_live(live, Expect(), sample, 0, sample.trace_id) == []


def test_a_missing_decline_fails(sample: RunDetail) -> None:
    live = _live(declines_include=[[101, "EMEA"], [201, "APAC"]])
    assert score_live(live, Expect(), sample, 0, sample.trace_id) == [
        "declines missing [[201, 'APAC']]"
    ]


def test_safety_invariants_fail_the_case(sample: RunDetail) -> None:
    leaked = score_live(
        _live(), Expect(forbidden_evidence_prefixes=["sales:"]), sample, 0, sample.trace_id
    )
    assert leaked and leaked[0].startswith("forbidden evidence")
    assert score_live(_live(), Expect(), sample, 1, sample.trace_id) == ["tickets 1 > 0"]
    assert score_live(_live(), Expect(tickets=1), sample, 1, sample.trace_id) == []
    wrong_trace = score_live(_live(), Expect(), sample, 0, "f" * 32)
    assert wrong_trace and wrong_trace[0].startswith("trace id")


def test_outcome_findings_and_cited_documents(sample: RunDetail) -> None:
    assert score_live(LiveExpect(outcomes=["abstained"]), Expect(), sample, 0, sample.trace_id) == [
        "status completed not in ['abstained']"
    ]
    assert score_live(_live(min_findings=4), Expect(), sample, 0, sample.trace_id) == [
        "findings 3 < 4"
    ]
    assert (
        score_live(
            _live(cites_documents=["doc-a-returns-policy"]), Expect(), sample, 0, sample.trace_id
        )
        == []
    )
    assert score_live(
        _live(cites_documents=["doc-b-supplier-policy"]), Expect(), sample, 0, sample.trace_id
    ) == ["no finding cites any of ['doc-b-supplier-policy']"]


def test_live_expectations_need_outcomes_or_unscored() -> None:
    assert LiveExpect(unscored=True).outcomes == []
    for bad in ({}, {"outcomes": ["completed"], "unscored": True}, {"outcomes": ["passed"]}):
        with pytest.raises(ValidationError):
            LiveExpect.model_validate(bad)


def test_every_workflow_case_in_the_corpus_has_a_live_expectation() -> None:
    corpus = load_corpus()
    assert corpus.dataset_version == "evals-v1.2.0"
    workflows = [c for c in corpus.cases if c.kind == "workflow"]
    assert len(workflows) == 42
    assert all(c.live is not None for c in workflows)
    assert all(c.live is None for c in corpus.cases if c.kind == "scenario")
    assert [c.id for c in workflows if c.live and c.live.unscored] == ["budget-02"]


# --- stubbed live corpus and benchmark -----------------------------------------------------


@pytest.fixture
def corpus() -> Corpus:
    def case(case_id: str, live: dict[str, Any]) -> Case:
        return Case(
            id=case_id,
            category="normal",
            description="stubbed workflow",
            kind="workflow",
            task_text="Analyze synthetic sales",
            turns=[{"text": "mock answer"}],
            expect=Expect(status="completed", findings=1),
            live=LiveExpect.model_validate(live),
        )

    return Corpus(
        dataset_version="evals-test-v1",
        cases=[
            case("ok-01", {"outcomes": ["completed", "abstained"]}),
            case("wrong-01", {"outcomes": ["abstained"]}),
            case("skip-01", {"unscored": True}),
        ],
    )


@pytest.fixture
def stubbed(monkeypatch: pytest.MonkeyPatch) -> None:
    async def run(request: TaskRequest, deps: RunDependencies) -> RunDetail:
        await deps.gateway.generate(
            ModelRequest(
                run_id=request.run_id,
                messages=[Message(role="user", content=request.task_text)],
                max_output_tokens=10,
            )
        )
        return RunDetail(
            run_id=request.run_id,
            thread_id=f"thread-{request.run_id}",
            trace_id=deps.new_trace_id(),
            tenant_id=request.tenant_id,
            user_id=request.user_id,
            task_text=request.task_text,
            status=RunStatus.COMPLETED,
            llm_provider=deps.llm_provider,
            llm_model=deps.llm_model,
            llm_calls=1,
            policy_decisions=[PolicyDecision(subject="t", decision="allow", reason_code="ALLOWED")],
        )

    monkeypatch.setattr(runner, "run_task", run)
    monkeypatch.setattr(benchmark, "run_task", run)
    monkeypatch.setattr(Env, "tickets", lambda self, tenant, run_id: 0)


def _provider() -> LiteLLMProvider:
    return LiteLLMProvider(
        registry=hosted_registry(),
        completion=stub_completion([{"text": "hosted answer"}] * 6),
        budget_usd=10.0,
        total_budget_usd=10.0,
        cost_estimator=lambda model, prompt, completion: 0.1,
    )


@pytest.mark.usefixtures("stubbed")
def test_live_corpus_reports_live_outcomes_beside_mock_trajectory(corpus: Corpus) -> None:
    report = runner.run_corpus(corpus, analytics_dsn="u", app_dsn="u", live_provider=_provider())
    by_id = {r.case_id: r for r in report.results}
    assert (by_id["ok-01"].live_passed, by_id["wrong-01"].live_passed) == (True, False)
    assert by_id["skip-01"].live_passed is None
    assert (report.live_scored, report.live_passed, report.live_unscored) == (2, 1, ["skip-01"])
    assert report.live_by_category == {"normal": {"total": 2, "passed": 1}}
    # The mock-trajectory score is unchanged: findings 0 != 1 fails all three.
    assert report.passed == 0
    assert all(
        r.observed["errors"] == [] and "abstain_reason" in r.observed for r in report.results
    )


@pytest.mark.usefixtures("stubbed")
def test_mock_corpus_records_errors_but_is_not_live_scored(corpus: Corpus) -> None:
    report = runner.run_corpus(corpus, analytics_dsn="u", app_dsn="u")
    assert (report.live_scored, report.live_passed, report.live_unscored) == (0, 0, [])
    assert all(r.live_passed is None for r in report.results)
    assert all("errors" in r.observed for r in report.results)


@pytest.mark.usefixtures("stubbed")
def test_live_benchmark_recommends_from_live_outcomes(corpus: Corpus, tmp_path: Path) -> None:
    report = benchmark.run_benchmark(
        corpus, analytics_dsn="u", app_dsn="u", live_provider=_provider()
    )
    for name in ("single", "specialists"):
        assert (report.aggregates[name].live_scored, report.aggregates[name].live_success) == (2, 1)
    assert report.recommendation == "keep_single_workflow"
    assert "live outcomes" in report.rationale
    _, md_path = benchmark.write_benchmark(report, tmp_path)
    text = md_path.read_text(encoding="utf-8")
    assert "Live outcome success (D-018 rubric) | 1/2 | 1/2" in text
    assert "Mock-trajectory expectations met" in text
