"""Compute chunk embeddings (run as the schema owner, after seeding)."""

import psycopg

from agentops_retrieval.embedding import Embedder, to_pgvector


def index_chunks(conn: psycopg.Connection, embedder: Embedder) -> int:
    """Embed every chunk not yet embedded by ``embedder.model_id``; return how many changed."""
    with conn.transaction():
        rows = conn.execute(
            "SELECT id, text FROM document_chunks"
            " WHERE embedding_model IS DISTINCT FROM %s ORDER BY id",
            (embedder.model_id,),
        ).fetchall()
        if not rows:
            return 0
        vectors = embedder.embed([text for _, text in rows])
        with conn.cursor() as cur:
            cur.executemany(
                "UPDATE document_chunks SET embedding = %s::vector, embedding_model = %s"
                " WHERE id = %s",
                [
                    (to_pgvector(vector), embedder.model_id, chunk_id)
                    for (chunk_id, _), vector in zip(rows, vectors, strict=True)
                ],
            )
    return len(rows)
