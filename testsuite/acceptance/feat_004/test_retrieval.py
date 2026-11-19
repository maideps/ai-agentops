"""feat-004 (FR-003): deterministic embeddings and permission-filtered retrieval."""

import math

import psycopg
import pytest

from agentops_data.access import MAX_RETRIEVAL_K
from agentops_retrieval.embedding import HashingEmbedder, tokens
from agentops_retrieval.search import search_documents

QUERY = "company policy on returns and pricing in 2026-Q3"


def test_hashing_embedder_is_deterministic_and_normalized() -> None:
    embedder = HashingEmbedder()
    [first] = embedder.embed([QUERY])
    [second] = embedder.embed([QUERY])

    assert first == second
    assert len(first) == embedder.dimensions
    assert math.isclose(math.sqrt(sum(value * value for value in first)), 1.0)
    assert tokens("The Jackets and Prices") == ["jacket", "price"]


@pytest.mark.integration
@pytest.mark.parametrize(
    ("user_id", "restricted_visible"), [("user-a-analyst", False), ("user-a-admin", True)]
)
def test_retrieval_filters_by_role_before_ranking(
    seeded_db: str, analytics_dsn: str, user_id: str, restricted_visible: bool
) -> None:
    with psycopg.connect(analytics_dsn) as conn:
        hits = search_documents(
            conn,
            HashingEmbedder(),
            tenant_id="demo-a",
            user_id=user_id,
            query="Q3 camping stove stockist decision",
            k=MAX_RETRIEVAL_K,
        )

    ids = [hit.id for hit in hits]
    assert ("doc-a-board-notes#0" in ids) is restricted_visible
    assert all(hit.id.startswith("doc-a-") for hit in hits)
    assert [hit.distance for hit in hits] == sorted(hit.distance for hit in hits)


@pytest.mark.integration
def test_policy_query_ranks_the_policy_chunks_first(seeded_db: str, analytics_dsn: str) -> None:
    with psycopg.connect(analytics_dsn) as conn:
        hits = search_documents(
            conn, HashingEmbedder(), tenant_id="demo-a", user_id="user-a-analyst", query=QUERY, k=2
        )

    assert {hit.id for hit in hits} == {"doc-a-pricing-guidelines#1", "doc-a-returns-policy#1"}
