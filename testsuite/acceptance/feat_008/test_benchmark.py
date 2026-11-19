"""feat-008 (FR-016, NFR-006, NFR-008): the orchestration benchmark runs reproducibly in mock
mode on the evaluation corpus, writes a versioned results file, labels what it can and cannot
show, and keeps the simpler design unless the specialists measurably win."""

import json
from pathlib import Path
from typing import Any

import pytest

from agentops_evals.benchmark import (
    Aggregate,
    BenchmarkReport,
    recommend,
    run_benchmark,
    write_benchmark,
)
from agentops_evals.corpus import load_corpus


def _aggregate(**overrides: Any) -> Aggregate:
    base: dict[str, Any] = {
        "cases": 42,
        "task_success": 42,
        "task_success_rate": 1.0,
        "supported_finding_rate": 1.0,
        "mean_llm_calls": 2.0,
        "mean_tool_calls": 2.0,
        "mean_tokens": 300.0,
        "latency_ms_p50": 100.0,
        "latency_ms_p95": 200.0,
        "cost_usd_total": 0.0,
    }
    return Aggregate.model_validate({**base, **overrides})


def test_ties_and_losses_keep_the_simpler_orchestration() -> None:
    baseline = _aggregate()

    assert recommend(baseline, _aggregate(mean_llm_calls=3.0))[0] == "keep_single_workflow"
    assert (
        recommend(baseline, _aggregate(task_success=41, task_success_rate=41 / 42))[0]
        == "keep_single_workflow"
    )
    assert (
        recommend(_aggregate(task_success=40, task_success_rate=40 / 42), baseline)[0]
        == "adopt_specialists"
    )


@pytest.fixture(scope="module")
def benchmark(
    seeded_db: str, analytics_dsn: str, app_dsn: str
) -> tuple[BenchmarkReport, BenchmarkReport]:
    corpus = load_corpus()
    first = run_benchmark(corpus, analytics_dsn=analytics_dsn, app_dsn=app_dsn)
    second = run_benchmark(corpus, analytics_dsn=analytics_dsn, app_dsn=app_dsn)
    return first, second


@pytest.mark.integration
def test_both_orchestrations_run_the_same_workflow_cases(
    benchmark: tuple[BenchmarkReport, BenchmarkReport],
) -> None:
    report, _ = benchmark
    workflow_ids = [c.id for c in load_corpus().cases if c.kind == "workflow"]

    assert report.sample_size == len(workflow_ids) == 42
    assert [r.case_id for r in report.cases] == workflow_ids
    assert {r.orchestration for r in report.runs} == {"single", "specialists"}
    assert report.mode == "mock"
    assert report.hosted_model_numbers is None
    assert report.dataset_version == load_corpus().dataset_version
    assert report.git_sha and report.model == "mock-deterministic-v1"
    assert set(report.prompt_versions) == {"single", "specialists"}
    assert report.limitations


@pytest.mark.integration
def test_measured_fields_are_reproducible(
    benchmark: tuple[BenchmarkReport, BenchmarkReport],
) -> None:
    first, second = benchmark

    assert first.deterministic_view() == second.deterministic_view()


@pytest.mark.integration
def test_results_keep_the_simpler_design_and_say_why(
    benchmark: tuple[BenchmarkReport, BenchmarkReport],
) -> None:
    report, _ = benchmark
    single, specialists = report.aggregates["single"], report.aggregates["specialists"]

    assert specialists.task_success <= single.task_success
    assert specialists.mean_llm_calls > single.mean_llm_calls
    assert report.recommendation == "keep_single_workflow"
    assert "model call" in report.rationale


@pytest.mark.integration
def test_results_file_and_report_are_written(
    benchmark: tuple[BenchmarkReport, BenchmarkReport], tmp_path: Path
) -> None:
    report, _ = benchmark

    json_path, md_path = write_benchmark(report, tmp_path)

    stored = json.loads(json_path.read_text(encoding="utf-8"))
    assert stored["benchmark_version"] == report.benchmark_version
    assert json_path.name == f"results-{report.mode}.json"
    text = md_path.read_text(encoding="utf-8")
    for needle in (
        "Sample size: 42",
        "mock",
        "Limitations",
        report.dataset_version,
        "keep_single_workflow",
    ):
        assert needle in text
