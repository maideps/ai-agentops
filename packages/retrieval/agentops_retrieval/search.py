"""Permission-filtered semantic search over the caller's documents."""

import psycopg

from agentops_data.access import RetrievedChunk, nearest_chunks
from agentops_retrieval.embedding import Embedder, to_pgvector


def search_documents(
    conn: psycopg.Connection,
    embedder: Embedder,
    *,
    tenant_id: str,
    user_id: str,
    query: str,
    k: int,
) -> list[RetrievedChunk]:
    [vector] = embedder.embed([query])
    return nearest_chunks(
        conn,
        tenant_id,
        user_id,
        query_vector=to_pgvector(vector),
        embedding_model=embedder.model_id,
        k=k,
    )
