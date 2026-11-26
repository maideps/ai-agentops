"""Benchmark-only fixed BM25 candidate; never used by production document search."""

import hashlib
import json
import math
from collections import Counter

import psycopg
from pydantic import BaseModel, ConfigDict

from agentops_data.access import MAX_RETRIEVAL_K, Chunk, document_chunks, documents_for_user
from agentops_retrieval.benchmark import (
    Aggregate,
    RetrievalDataset,
    RetrievalMetrics,
    RetrievalReport,
    relevance_metrics,
    run_benchmark,
    summarize,
)
from agentops_retrieval.embedding import Embedder, tokens

K1 = 1.2
B = 0.75


class BM25Hit(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)

    chunk_id: str
    document_id: str
    text_sha256: str
    score: float


class CandidateResult(RetrievalMetrics):
    case_id: str
    catalog_sha256: str
    hits: list[BM25Hit]


class ComparisonReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)

    git_sha: str
    candidate: str
    parameters: dict[str, float]
    baseline: RetrievalReport
    candidate_aggregate: Aggregate
    results: list[CandidateResult]
    limitations: list[str]


def rank_bm25(chunks: list[Chunk], query: str, *, k: int) -> list[BM25Hit]:
    """Score only the supplied permitted catalog; keep zero-score candidates, tied by id."""
    if not 1 <= k <= MAX_RETRIEVAL_K:
        raise ValueError(f"k must be between 1 and {MAX_RETRIEVAL_K}")
    if not chunks:
        return []
    counts = [Counter(tokens(chunk.text)) for chunk in chunks]
    lengths = [sum(count.values()) for count in counts]
    average_length = sum(lengths) / len(chunks)
    query_terms = sorted(set(tokens(query)))
    frequencies = Counter(term for count in counts for term in count)
    hits = []
    for chunk, count, length in zip(chunks, counts, lengths, strict=True):
        value = 0.0
        for term in query_terms:
            frequency = count[term]
            if not frequency:
                continue
            idf = math.log(1 + (len(chunks) - frequencies[term] + 0.5) / (frequencies[term] + 0.5))
            value += (
                idf
                * frequency
                * (K1 + 1)
                / (frequency + K1 * (1 - B + B * length / average_length))
            )
        hits.append(
            BM25Hit(
                chunk_id=chunk.id,
                document_id=chunk.document_id,
                text_sha256=chunk.text_sha256,
                score=value,
            )
        )
    return sorted(hits, key=lambda hit: (-hit.score, hit.chunk_id))[:k]


def run_comparison(
    conn: psycopg.Connection, embedder: Embedder, dataset: RetrievalDataset, *, git_sha: str
) -> ComparisonReport:
    results = []
    with conn.transaction():
        conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        baseline = run_benchmark(conn, embedder, dataset, git_sha=git_sha)
        for case in dataset.cases:
            documents = documents_for_user(conn, case.tenant_id, case.user_id)
            allowed = {document.id for document in documents}
            chunks = [
                chunk
                for document in documents
                for chunk in document_chunks(conn, case.tenant_id, case.user_id, document.id)
            ]
            catalog = sorted((chunk.id, chunk.text_sha256) for chunk in chunks)
            catalog_hash = hashlib.sha256(
                json.dumps(catalog, separators=(",", ":")).encode("utf-8")
            ).hexdigest()
            hits = rank_bm25(chunks, case.query, k=case.k)
            recall, reciprocal_rank = relevance_metrics(case, [hit.chunk_id for hit in hits])
            results.append(
                CandidateResult(
                    case_id=case.id,
                    catalog_sha256=catalog_hash,
                    hits=hits,
                    recall_at_k=recall,
                    reciprocal_rank=reciprocal_rank,
                    forbidden_hits=[
                        hit.chunk_id
                        for hit in hits
                        if hit.document_id not in allowed
                        or hit.document_id in case.forbidden_document_ids
                    ],
                )
            )
    return ComparisonReport(
        git_sha=baseline.git_sha,
        candidate="bm25-v1",
        parameters={"k1": K1, "b": B},
        baseline=baseline,
        candidate_aggregate=summarize(results),
        results=results,
        limitations=[
            "Exploratory comparison on already inspected, tiny agent-curated synthetic corpora; "
            "not held-out quality, end-to-end answer quality or grounds for production adoption.",
            "BM25 uses existing hashing tokenization, unique query terms, fixed k1=1.2 and b=0.75; "
            "no parameter tuning, synonyms, stemming changes or score threshold.",
            "Both rankers use one repeatable-read, read-only snapshot. BM25 scores all permitted "
            "chunks with statistics computed only from that principal's catalog.",
            "BM25 scores (larger is better) are not vector distances (smaller is better). "
            "Zero-overlap candidates are retained, so this does not measure abstention.",
            "Catalog hashes cover sorted permitted chunk ids/source hashes, not retrieved text. "
            "No model calls, downloads, writes, production ranking or judgment changes.",
            "Full-catalog Python scoring is an experiment for the small seed, not a scalable "
            "production implementation or a latency benchmark.",
        ],
    )
