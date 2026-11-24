"""Measure the existing retrieval baseline on versioned synthetic judgments, without LLMs."""

import hashlib
from pathlib import Path
from statistics import fmean
from typing import Self

import psycopg
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from agentops_data.access import (
    MAX_RETRIEVAL_K,
    RetrievedChunk,
    document_chunks,
    documents_for_user,
)
from agentops_retrieval.embedding import Embedder
from agentops_retrieval.search import search_documents

DEFAULT_DATASET = Path("datasets/retrieval/v1/queries.json")


class _Model(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)


class RetrievalCase(_Model):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,63}$")
    tenant_id: str
    user_id: str
    query: str = Field(min_length=1, max_length=2000)
    k: int = Field(default=3, ge=1, le=MAX_RETRIEVAL_K)
    relevant_chunk_ids: list[str] = Field(max_length=100)
    forbidden_document_ids: list[str] = Field(default_factory=list, max_length=100)

    @field_validator("query")
    @classmethod
    def _nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("query cannot be blank")
        return value


class RetrievalDataset(_Model):
    version: str = Field(min_length=1)
    cases: list[RetrievalCase] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def _unique_ids(self) -> Self:
        if len({case.id for case in self.cases}) != len(self.cases):
            raise ValueError("duplicate retrieval case id")
        return self


class Hit(_Model):
    chunk_id: str
    document_id: str
    text_sha256: str
    distance: float


class QueryResult(_Model):
    case_id: str
    tenant_id: str
    user_id: str
    query: str
    k: int
    relevant_chunk_ids: list[str]
    hits: list[Hit]
    recall_at_k: float | None
    reciprocal_rank: float | None
    forbidden_hits: list[str]


class Aggregate(_Model):
    queries: int
    answerable_queries: int
    no_accessible_evidence_queries: int
    mean_recall_at_k: float | None
    mrr: float | None
    forbidden_hits: int


class RetrievalReport(_Model):
    dataset_version: str
    dataset_sha256: str
    git_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    embedding_model: str
    aggregate: Aggregate
    results: list[QueryResult]
    limitations: list[str]


def load_dataset(path: Path = DEFAULT_DATASET) -> RetrievalDataset:
    return RetrievalDataset.model_validate_json(path.read_text(encoding="utf-8"))


def score(
    case: RetrievalCase,
    hits: list[RetrievedChunk],
    *,
    allowed_document_ids: set[str] | None = None,
) -> QueryResult:
    ranked = hits[: case.k]
    relevant = set(case.relevant_chunk_ids)
    retrieved = {hit.id for hit in ranked}
    first = next((rank for rank, hit in enumerate(ranked, 1) if hit.id in relevant), None)
    return QueryResult(
        case_id=case.id,
        tenant_id=case.tenant_id,
        user_id=case.user_id,
        query=case.query,
        k=case.k,
        relevant_chunk_ids=case.relevant_chunk_ids,
        hits=[
            Hit(
                chunk_id=hit.id,
                document_id=hit.document_id,
                text_sha256=hit.text_sha256,
                distance=hit.distance,
            )
            for hit in ranked
        ],
        recall_at_k=len(relevant & retrieved) / len(relevant) if relevant else None,
        reciprocal_rank=(1 / first if first else 0.0) if relevant else None,
        forbidden_hits=[
            hit.id
            for hit in ranked
            if hit.document_id in case.forbidden_document_ids
            or (allowed_document_ids is not None and hit.document_id not in allowed_document_ids)
        ],
    )


def summarize(results: list[QueryResult]) -> Aggregate:
    recalls = [r.recall_at_k for r in results if r.recall_at_k is not None]
    ranks = [r.reciprocal_rank for r in results if r.reciprocal_rank is not None]
    return Aggregate(
        queries=len(results),
        answerable_queries=len(recalls),
        no_accessible_evidence_queries=len(results) - len(recalls),
        mean_recall_at_k=fmean(recalls) if recalls else None,
        mrr=fmean(ranks) if ranks else None,
        forbidden_hits=sum(len(result.forbidden_hits) for result in results),
    )


def run_benchmark(
    conn: psycopg.Connection, embedder: Embedder, dataset: RetrievalDataset, *, git_sha: str
) -> RetrievalReport:
    results = []
    for case in dataset.cases:
        documents = documents_for_user(conn, case.tenant_id, case.user_id)
        accessible_chunks = {
            chunk.id
            for document in documents
            for chunk in document_chunks(conn, case.tenant_id, case.user_id, document.id)
        }
        if not set(case.relevant_chunk_ids) <= accessible_chunks:
            raise ValueError(f"case {case.id}: relevant judgments must name accessible chunks")
        hits = search_documents(
            conn,
            embedder,
            tenant_id=case.tenant_id,
            user_id=case.user_id,
            query=case.query,
            k=case.k,
        )
        results.append(score(case, hits, allowed_document_ids={d.id for d in documents}))
    return RetrievalReport(
        dataset_version=dataset.version,
        dataset_sha256=hashlib.sha256(dataset.model_dump_json().encode("utf-8")).hexdigest(),
        git_sha=git_sha,
        embedding_model=embedder.model_id,
        aggregate=summarize(results),
        results=results,
        limitations=[
            "Small curated synthetic corpus with vocabulary overlap, not held-out real-world "
            "retrieval or end-to-end answer quality.",
            "Recall@k and MRR are macro-averages over queries with accessible relevant chunks. "
            "No-accessible-evidence queries are excluded, not scored as perfect.",
            "Nearest-neighbor retrieval always returns candidates when available; this "
            "benchmark does not measure abstention or add a relevance threshold.",
            "Only chunk ids, source hashes and distances are recorded, not retrieved text.",
        ],
    )
