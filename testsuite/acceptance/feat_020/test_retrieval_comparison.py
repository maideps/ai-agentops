"""A fixed lexical candidate is measured, not silently installed as the retriever."""

import hashlib
import math
from pathlib import Path

import psycopg
import pytest

from agentops_data.access import Chunk, UnknownPrincipalError, document_chunks, documents_for_user
from agentops_retrieval import __main__ as cli
from agentops_retrieval import comparison
from agentops_retrieval.benchmark import RetrievalDataset, load_dataset
from agentops_retrieval.comparison import BM25Hit, ComparisonReport, rank_bm25, run_comparison
from agentops_retrieval.embedding import HashingEmbedder


def _chunk(chunk_id: str, text: str) -> Chunk:
    return Chunk(
        id=chunk_id,
        document_id=chunk_id.split("#")[0],
        chunk_index=int(chunk_id.split("#")[1]),
        text=text,
        text_sha256=hashlib.sha256(text.encode()).hexdigest(),
    )


def test_bm25_uses_term_frequency_document_frequency_and_length_normalization() -> None:
    chunks = [_chunk("doc#0", "rain rain"), _chunk("doc#1", "rain boot"), _chunk("doc#2", "boot")]
    hits = rank_bm25(chunks, "rain", k=3)
    assert [hit.chunk_id for hit in hits] == ["doc#0", "doc#1", "doc#2"]
    idf = math.log(1 + (3 - 2 + 0.5) / (2 + 0.5))
    expected = idf * (2 * 2.2) / (2 + 1.2 * (0.25 + 0.75 * 2 / (5 / 3)))
    assert hits[0].score == pytest.approx(expected)
    assert hits[2].score == 0


@pytest.mark.parametrize("query", ["the and", "unmatched"])
def test_zero_overlap_keeps_candidates_with_stable_id_ties(query: str) -> None:
    chunks = [_chunk("doc#2", ""), _chunk("doc#1", "rain")]
    assert [hit.chunk_id for hit in rank_bm25(chunks, query, k=1)] == ["doc#1"]
    assert rank_bm25([], query, k=3) == []
    assert rank_bm25([_chunk("doc#0", "")], query, k=3)[0].score == 0


@pytest.mark.parametrize(
    "dataset_path",
    [Path("datasets/retrieval/v1/queries.json"), Path("datasets/retrieval/stress-v2/queries.json")],
)
@pytest.mark.integration
def test_real_cli_pairs_frozen_corpora_without_writes_or_forbidden_hits(
    seeded_db: str,
    analytics_dsn: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    dataset_path: Path,
) -> None:
    monkeypatch.setenv("ANALYTICS_DATABASE_URL", analytics_dsn)
    out = tmp_path / "comparison.json"
    args = [
        "compare",
        "--dataset",
        str(dataset_path),
        "--git-sha",
        "a" * 40,
        "--out",
        str(out),
    ]
    assert cli.main(args) == 0
    first = out.read_bytes()
    report = ComparisonReport.model_validate_json(first)
    assert cli.main(args) == 0
    assert out.read_bytes() == first
    assert report.baseline.aggregate.forbidden_hits == 0
    assert report.candidate_aggregate.forbidden_hits == 0
    assert report.baseline.aggregate.no_accessible_evidence_queries == 4
    assert report.candidate_aggregate.no_accessible_evidence_queries == 4
    assert len(report.results) == len(load_dataset(dataset_path).cases)
    with psycopg.connect(analytics_dsn) as conn:
        for pair, baseline in zip(report.results, report.baseline.results, strict=True):
            assert pair.case_id == baseline.case_id
            relevant = set(baseline.relevant_chunk_ids)
            retrieved = {hit.chunk_id for hit in pair.hits}
            assert pair.recall_at_k == (
                len(relevant & retrieved) / len(relevant) if relevant else None
            )
            first_rank = next(
                (i for i, hit in enumerate(pair.hits, 1) if hit.chunk_id in relevant), None
            )
            assert pair.reciprocal_rank == (
                (1 / first_rank if first_rank else 0) if relevant else None
            )
            documents = documents_for_user(conn, baseline.tenant_id, baseline.user_id)
            allowed = {
                chunk.id
                for document in documents
                for chunk in document_chunks(
                    conn, baseline.tenant_id, baseline.user_id, document.id
                )
            }
            assert retrieved <= allowed
            assert len(pair.catalog_sha256) == 64
            assert all(hit.text_sha256 and hit.score >= 0 for hit in pair.hits)
    assert b'"text":' not in first
    assert report.git_sha == report.baseline.git_sha == "a" * 40
    with (
        psycopg.connect(analytics_dsn) as conn,
        pytest.raises(psycopg.errors.InsufficientPrivilege),
    ):
        conn.execute("DELETE FROM document_chunks")


@pytest.mark.integration
def test_comparison_rejects_forbidden_judgments_and_cross_tenant_principals(
    seeded_db: str, analytics_dsn: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    case = (
        load_dataset()
        .cases[0]
        .model_copy(
            update={"user_id": "user-a-viewer", "relevant_chunk_ids": ["doc-a-board-notes#0"]}
        )
    )
    with psycopg.connect(analytics_dsn) as conn:
        observed_catalogs = []

        def checked_rank(chunks: list[Chunk], query: str, *, k: int) -> list[BM25Hit]:
            assert conn.execute("SHOW transaction_isolation").fetchone() == ("repeatable read",)
            assert conn.execute("SHOW transaction_read_only").fetchone() == ("on",)
            observed_catalogs.append({chunk.document_id for chunk in chunks})
            return rank_bm25(chunks, query, k=k)

        monkeypatch.setattr(comparison, "rank_bm25", checked_rank)
        run_comparison(
            conn,
            HashingEmbedder(),
            RetrievalDataset(
                version="viewer",
                cases=[case.model_copy(update={"relevant_chunk_ids": []})],
            ),
            git_sha="a" * 40,
        )
        assert observed_catalogs == [{"doc-a-press-kit"}]
        with pytest.raises(ValueError, match="accessible"):
            run_comparison(
                conn,
                HashingEmbedder(),
                RetrievalDataset(version="bad", cases=[case]),
                git_sha="a" * 40,
            )
        with pytest.raises(UnknownPrincipalError):
            run_comparison(
                conn,
                HashingEmbedder(),
                RetrievalDataset(
                    version="bad",
                    cases=[case.model_copy(update={"user_id": "user-b-analyst"})],
                ),
                git_sha="a" * 40,
            )


def test_comparison_cli_fails_explicitly_without_configuration(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "comparison.json"
    assert cli.main(["compare", "--git-sha", "a" * 40, "--out", str(out)]) == 2
    assert "ANALYTICS_DATABASE_URL" in capsys.readouterr().err
    assert not out.exists()


@pytest.mark.integration
def test_cli_exits_nonzero_for_a_forbidden_candidate_even_when_baseline_is_clean(
    seeded_db: str, analytics_dsn: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def forbidden_rank(chunks: list[Chunk], query: str, *, k: int) -> list[BM25Hit]:
        return [
            BM25Hit(
                chunk_id="forbidden#0",
                document_id="forbidden",
                text_sha256="a" * 64,
                score=1,
            )
        ]

    monkeypatch.setattr(comparison, "rank_bm25", forbidden_rank)
    monkeypatch.setenv("ANALYTICS_DATABASE_URL", analytics_dsn)
    out = tmp_path / "forbidden.json"
    assert cli.main(["compare", "--git-sha", "a" * 40, "--out", str(out)]) == 1
    report = ComparisonReport.model_validate_json(out.read_bytes())
    assert report.baseline.aggregate.forbidden_hits == 0
    assert report.candidate_aggregate.forbidden_hits == len(report.results)
