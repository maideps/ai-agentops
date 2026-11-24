"""Exercise the stress corpus through the existing read-only benchmark CLI."""

from pathlib import Path

import pytest

from agentops_retrieval.__main__ import main
from agentops_retrieval.benchmark import RetrievalDataset, RetrievalReport, load_dataset

STRESS = Path("datasets/retrieval/stress-v2/queries.json")


@pytest.mark.integration
def test_cli_selects_both_corpora_and_reproduces_stress_results(
    seeded_db: str, analytics_dsn: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("ANALYTICS_DATABASE_URL", analytics_dsn)
    dataset = load_dataset(STRESS)
    first, second, baseline = (tmp_path / name for name in ("first.json", "second.json", "v1.json"))
    for out in (first, second):
        assert (
            main(["benchmark", "--dataset", str(STRESS), "--git-sha", "a" * 40, "--out", str(out)])
            == 0
        )
    assert main(["benchmark", "--git-sha", "a" * 40, "--out", str(baseline)]) == 0
    assert first.read_bytes() == second.read_bytes()
    stress_report = RetrievalReport.model_validate_json(first.read_bytes())
    v1_report = RetrievalReport.model_validate_json(baseline.read_bytes())
    assert stress_report.dataset_sha256 != v1_report.dataset_sha256
    assert stress_report.embedding_model == v1_report.embedding_model
    assert [result.case_id for result in stress_report.results] == [
        case.id for case in dataset.cases
    ]
    assert any(len(result.relevant_chunk_ids) > 1 for result in stress_report.results)
    assert stress_report.aggregate.forbidden_hits == v1_report.aggregate.forbidden_hits == 0
    for result in stress_report.results:
        if not result.relevant_chunk_ids:
            assert result.recall_at_k is None and result.reciprocal_rank is None
    assert {case.query for case in dataset.cases}.isdisjoint(
        case.query for case in load_dataset().cases
    )


@pytest.mark.integration
def test_partially_inaccessible_multichunk_judgments_fail_without_a_report(
    seeded_db: str,
    analytics_dsn: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("ANALYTICS_DATABASE_URL", analytics_dsn)
    case = next(case for case in load_dataset(STRESS).cases if case.id == "multi-company-returns")
    denied = case.model_copy(update={"user_id": "user-a-viewer"})
    dataset = RetrievalDataset(version="inaccessible-test", cases=[denied])
    bad = tmp_path / "judgments.json"
    bad.write_text(dataset.model_dump_json(), encoding="utf-8")
    out = tmp_path / "out.json"
    assert main(["benchmark", "--dataset", str(bad), "--git-sha", "a" * 40, "--out", str(out)]) == 2
    assert "accessible" in capsys.readouterr().err
    assert not out.exists()
