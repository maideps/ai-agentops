# Offline BM25 retrieval comparison

Measured 2026-11-26 at implementation commit
`2268b1d2a7e72089edbc57352ec4a6d0fa5bdae8`, using one freshly seeded/indexed isolated
database: seven synthetic documents, 16 chunks, `hashing-v1-256`. No source, index,
query, judgment or parameter changes occurred between the two corpus runs.
No hosted calls, model downloads or spend.

The candidate is benchmark-only BM25 (`k1=1.2`, `b=0.75`) with the existing tokenizer,
unique query terms, no relevance threshold and chunk-id tie breaks. Parameters were
fixed before these measurements, not selected from a search over the corpora.
Each run pairs both rankers within one read-only, repeatable-read snapshot using the
analytics login. BM25 statistics see only that principal's permitted chunk catalog.

## Measurements

| Corpus / ranker | Answerable / unscored | Mean Recall@3 | MRR | Forbidden hits |
|---|---|---|---|---|
| v1 / hashing baseline | 12 / 4 | 1.0000 | 1.0000 | 0 |
| v1 / BM25 | 12 / 4 | 1.0000 | 1.0000 | 0 |
| stress v2 / hashing baseline | 24 / 4 | 0.7639 | 0.7361 | 0 |
| stress v2 / BM25 | 24 / 4 | 0.8264 | 0.7986 | 0 |

Both stress macro metrics rise by 0.0625 on these judgments. Complete/partial/missed
stress queries change from 16/4/4 to 17/5/2. Better averages do not mean every query
improves: one previously complete paraphrase becomes a total miss, and one complete
multi-chunk query becomes partial.

| Stress family | Baseline / BM25 Recall@3 | Baseline / BM25 MRR |
|---|---|---|
| Paraphrase (8) | 0.7500 / 0.7500 | 0.5417 / 0.6042 |
| Multi-chunk (8) | 0.6667 / 0.7292 | 0.8750 / 1.0000 |
| Distractor (8) | 0.8750 / 1.0000 | 0.7917 / 0.7917 |

Every changed answerable case is listed below, including rank-only regressions.
The other 13 stress answerable cases and all 12 v1 answerable cases have unchanged
Recall@3 and reciprocal rank. Access-negative cases remain unscored.

| Case | Baseline / BM25 Recall@3 | Baseline / BM25 reciprocal rank |
|---|---|---|
| paraphrase-unused | 0 / 1 | 0 / 1 |
| paraphrase-worn | 1 / 1 | 1/2 / 1 |
| paraphrase-proof | 1 / 1 | 1 / 1/2 |
| paraphrase-cooking | 1 / 0 | 1 / 0 |
| paraphrase-inspection | 1 / 1 | 1/2 / 1 |
| multi-return-terms | 1/2 / 1 | 1 / 1 |
| multi-pricing-authority | 0 / 1/2 | 0 / 1 |
| multi-audit-duration | 1 / 1/2 | 1 / 1 |
| distractor-stove-list | 1 / 1 | 1 / 1/2 |
| distractor-return-proof | 0 / 1 | 0 / 1/3 |
| distractor-seasonal-check | 1 / 1 | 1/3 / 1/2 |

## Evidence and interpretation

[Control JSON](control.json) and [stress JSON](stress.json) retain the paired
per-query hits, source hashes and metrics, canonical dataset versions/hashes, full
permitted-catalog fingerprints, fixed parameters and supplied commit SHA.
Vector distances and BM25 scores are separate fields with opposite ordering
directions; their numeric magnitudes are not comparable.

All repeated principal catalogs have identical fingerprints across both runs.
Common retrieved chunk ids have identical source hashes across rankers. The vector
aggregates reproduce the historical v1 and stress baselines; those historical
artifacts, frozen corpora and production retrieval code remain unchanged.

**Decision: do not adopt BM25 as the production default.** This fixed candidate
deserves an independent held-out comparison, not deployment or further tuning on
these questions. It improves some lexical matches but still misses two stress cases,
and introduces the cooking and audit-duration recall regressions above. No causal
attribution to hashing collisions, term weighting or semantics is established.

These are tiny, agent-curated, already inspected synthetic corpora, not held-out
real-world retrieval or end-to-end report quality. Lexical BM25 does not resolve
synonyms or negation. Zero forbidden hits covers these cases, not universal access
safety. Zero-overlap candidates are retained: neither ranker is being evaluated for
abstention. Full-catalog Python scoring is not a scalable production implementation
or a latency benchmark.

See the [procedure](../../../docs/retrieval-baseline.md#offline-bm25-comparison).
Use a new report directory for future experiments; never overwrite this evidence.
