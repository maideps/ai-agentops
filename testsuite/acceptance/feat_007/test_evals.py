"""feat-007 (NFR-006, NFR-007, NFR-002): the versioned 50-case corpus runs in mock mode, records
its provenance, and a failing case is traceable to its spans."""

import re
from typing import Any

import pytest

from agentops_evals.corpus import Expect, load_corpus
from agentops_evals.runner import EvalReport, run_corpus

SPEC_SPLIT = {
    "normal": 10,
    "multi_source": 8,
    "missing": 6,
    "tool_schema": 6,
    "injection": 8,
    "access": 4,
    "reliability": 6,
    "budget": 2,
}


def test_corpus_is_versioned_with_the_spec_split() -> None:
    corpus = load_corpus()

    assert re.fullmatch(r"evals-v\d+\.\d+\.\d+", corpus.dataset_version)
    assert len(corpus.cases) == 50
    assert len({c.id for c in corpus.cases}) == 50
    counts: dict[str, int] = {}
    for case in corpus.cases:
        counts[case.category] = counts.get(case.category, 0) + 1
    assert counts == SPEC_SPLIT


@pytest.fixture(scope="module")
def report(seeded_db: str, analytics_dsn: str, app_dsn: str) -> EvalReport:
    return run_corpus(load_corpus(), analytics_dsn=analytics_dsn, app_dsn=app_dsn)


@pytest.mark.integration
def test_all_fifty_cases_pass_in_mock_mode(report: EvalReport) -> None:
    failing = {r.case_id: r.failures for r in report.results if not r.passed}

    assert failing == {}
    assert (report.total, report.passed) == (50, 50)
    assert report.by_category == {k: {"total": v, "passed": v} for k, v in SPEC_SPLIT.items()}


@pytest.mark.integration
def test_report_records_provenance(report: EvalReport) -> None:
    assert report.dataset_version == load_corpus().dataset_version
    assert report.git_sha and report.git_sha != "unknown"
    assert (report.provider, report.model) == ("mock", "mock-deterministic-v1")
    assert re.fullmatch(r"[0-9a-f]{12}", report.prompt_version)
    assert report.policy_version
    for result in report.results:
        assert re.fullmatch(r"[0-9a-f]{32}", result.trace_id)
        assert result.run_id.startswith(f"eval-{result.case_id}-")


@pytest.mark.integration
def test_a_failing_case_is_traceable_to_its_spans(
    seeded_db: str, analytics_dsn: str, app_dsn: str, span_exporter: Any
) -> None:
    corpus = load_corpus()
    good = next(c for c in corpus.cases if c.id == "normal-01")
    broken = good.model_copy(update={"expect": Expect(status="abstained")})
    span_exporter.clear()

    result = run_corpus(
        corpus.model_copy(update={"cases": [broken]}),
        analytics_dsn=analytics_dsn,
        app_dsn=app_dsn,
    ).results[0]

    assert not result.passed
    assert result.failures == ["status completed != abstained"]
    traced = {
        s.name
        for s in span_exporter.get_finished_spans()
        if format(s.context.trace_id, "032x") == result.trace_id
    }
    assert {"eval.case", "agent.run", "llm.generate", "tool.execute"} <= traced
