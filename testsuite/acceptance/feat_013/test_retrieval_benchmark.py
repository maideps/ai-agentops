"""Retrieval scores measure ranked relevant chunks, not access checks or model quality."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from agentops_data.access import RetrievedChunk
from agentops_retrieval import __main__ as cli
from agentops_retrieval.benchmark import (
    RetrievalCase,
    RetrievalDataset,
    RetrievalReport,
    load_dataset,
    score,
    summarize,
)


def _hit(document: str, chunk: int = 0) -> RetrievedChunk:
    return RetrievedChunk(
        id=f"{document}#{chunk}",
        document_id=document,
        document_title="synthetic",
        source_uri="synthetic://test",
        chunk_index=chunk,
        text="not included in the report",
        text_sha256="a" * 64,
        distance=0.5,
    )


def _case(**changes: object) -> RetrievalCase:
    return RetrievalCase.model_validate(
        {
            "id": "test",
            "tenant_id": "demo-a",
            "user_id": "user-a-analyst",
            "query": "synthetic query",
            "k": 3,
            "relevant_chunk_ids": ["doc-a#0", "doc-b#0"],
            **changes,
        }
    )


def test_scores_respect_rank_cutoff_and_all_relevant_judgments() -> None:
    result = score(_case(), [_hit("other"), _hit("doc-a"), _hit("another"), _hit("doc-b")])
    assert result.recall_at_k == 0.5
    assert result.reciprocal_rank == 0.5
    assert [hit.chunk_id for hit in result.hits] == ["other#0", "doc-a#0", "another#0"]
    assert "not included in the report" not in result.model_dump_json()


def test_unanswerable_queries_are_not_perfect_scores_or_in_the_denominator() -> None:
    absent = score(_case(id="absent", relevant_chunk_ids=[]), [_hit("other")])
    missed = score(_case(id="missed"), [])
    found = score(_case(id="found"), [_hit("doc-a"), _hit("doc-b")])
    assert absent.recall_at_k is None and absent.reciprocal_rank is None
    assert missed.recall_at_k == missed.reciprocal_rank == 0.0
    aggregate = summarize([absent, missed, found])
    assert aggregate.answerable_queries == 2
    assert aggregate.no_accessible_evidence_queries == 1
    assert aggregate.mean_recall_at_k == aggregate.mrr == 0.5


def test_forbidden_hits_are_reported_even_for_unanswerable_queries() -> None:
    result = score(
        _case(relevant_chunk_ids=[], forbidden_document_ids=["hidden"]),
        [_hit("hidden"), _hit("other")],
    )
    assert result.forbidden_hits == ["hidden#0"]
    aggregate = summarize([result])
    assert aggregate.forbidden_hits == 1
    assert aggregate.mean_recall_at_k is None and aggregate.mrr is None


def test_runtime_access_catalog_catches_unlisted_forbidden_sources() -> None:
    result = score(_case(), [_hit("not-granted")], allowed_document_ids={"doc-a", "doc-b"})
    assert result.forbidden_hits == ["not-granted#0"]


def test_duplicate_case_ids_are_invalid() -> None:
    with pytest.raises(ValidationError, match="duplicate"):
        RetrievalDataset(version="retrieval-v1", cases=[_case(), _case()])


@pytest.mark.parametrize("changes", [{"k": 0}, {"k": 21}, {"query": "  "}])
def test_invalid_queries_fail_explicitly(changes: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        _case(**changes)


def test_cli_requires_a_readonly_database_url_and_records_no_fake_result(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    out = tmp_path / "result.json"
    assert cli.main(["benchmark", "--git-sha", "a" * 40, "--out", str(out)]) == 2
    assert "ANALYTICS_DATABASE_URL" in capsys.readouterr().err
    assert not out.exists()


def test_cli_reports_output_errors_explicitly(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    parent = tmp_path / "not-a-directory"
    parent.write_text("preserve this file", encoding="utf-8")
    result = score(_case(), [])
    report = RetrievalReport(
        dataset_version="test",
        dataset_sha256="a" * 64,
        git_sha="a" * 40,
        embedding_model="hashing-v1-256",
        aggregate=summarize([result]),
        results=[result],
        limitations=[],
    )
    monkeypatch.setenv("ANALYTICS_DATABASE_URL", "stubbed")
    monkeypatch.setattr("psycopg.connect", MagicMock())
    monkeypatch.setattr(cli, "run_benchmark", MagicMock(return_value=report))
    assert cli.main(["benchmark", "--git-sha", "a" * 40, "--out", str(parent / "out.json")]) == 2
    assert "benchmark error:" in capsys.readouterr().err
    assert parent.read_text(encoding="utf-8") == "preserve this file"


@pytest.mark.integration
def test_versioned_corpus_is_reproducible_and_never_returns_forbidden_documents(
    seeded_db: str, analytics_dsn: str
) -> None:
    import psycopg

    from agentops_retrieval.benchmark import run_benchmark
    from agentops_retrieval.embedding import HashingEmbedder

    dataset = load_dataset()
    with psycopg.connect(analytics_dsn) as conn:
        first = run_benchmark(conn, HashingEmbedder(), dataset, git_sha="a" * 40)
        second = run_benchmark(conn, HashingEmbedder(), dataset, git_sha="a" * 40)
    assert first.model_dump() == second.model_dump()
    assert first.aggregate.forbidden_hits == 0
    assert first.aggregate.answerable_queries == 12
    assert first.aggregate.no_accessible_evidence_queries == 4
    assert first.aggregate.mean_recall_at_k is not None
    assert first.aggregate.mrr is not None
    assert 0 <= first.aggregate.mean_recall_at_k <= 1
    assert 0 <= first.aggregate.mrr <= 1
    assert first.dataset_version == dataset.version
    assert len(first.dataset_sha256) == 64
    assert first.embedding_model == "hashing-v1-256"
    assert all(hit.text_sha256 for result in first.results for hit in result.hits)


@pytest.mark.integration
def test_inaccessible_relevance_judgments_fail_instead_of_becoming_misses(
    seeded_db: str, analytics_dsn: str
) -> None:
    import psycopg

    from agentops_retrieval.benchmark import run_benchmark
    from agentops_retrieval.embedding import HashingEmbedder

    dataset = RetrievalDataset(
        version="bad-judgment",
        cases=[
            _case(
                user_id="user-a-viewer",
                relevant_chunk_ids=["doc-a-board-notes#0"],
            )
        ],
    )
    with psycopg.connect(analytics_dsn) as conn, pytest.raises(ValueError, match="accessible"):
        run_benchmark(conn, HashingEmbedder(), dataset, git_sha="a" * 40)
