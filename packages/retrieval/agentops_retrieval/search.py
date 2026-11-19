"""Permission-filtered semantic search over the caller's documents."""

import psycopg

from agentops_data.access import RetrievedChunk, nearest_chunks
from agentops_retrieval.embedding import Embedder, to_pgvector
from agentops_telemetry.tracing import span


def search_documents(
    conn: psycopg.Connection,
    embedder: Embedder,
    *,
    tenant_id: str,
    user_id: str,
    query: str,
    k: int,
) -> list[RetrievedChunk]:
    with span(
        "rag.retrieve",
        {"agentops.tenant_id": tenant_id, "rag.k": k, "rag.embedding_model": embedder.model_id},
    ) as current:
        [vector] = embedder.embed([query])
        hits = nearest_chunks(
            conn,
            tenant_id,
            user_id,
            query_vector=to_pgvector(vector),
            embedding_model=embedder.model_id,
            k=k,
        )
        current.set_attribute("rag.hits", len(hits))
    return hits
