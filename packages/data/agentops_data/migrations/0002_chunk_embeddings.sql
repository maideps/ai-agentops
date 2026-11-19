-- Chunk embeddings for permission-filtered retrieval (D-008).
-- 256 dimensions = HashingEmbedder; another embedder needs a migration for its dimension.
-- No ANN index yet: exact search is fine at synthetic-corpus size.

ALTER TABLE document_chunks
    ADD COLUMN embedding vector(256),
    ADD COLUMN embedding_model text;
