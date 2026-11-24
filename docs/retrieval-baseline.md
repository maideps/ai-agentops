# Retrieval relevance baseline

The feat-013 benchmark measures the existing `HashingEmbedder` and permission-filtered
pgvector ranking. It does not change search, call a model, or download an embedder.

## Reproduce

Use synthetic data only. Migrate, seed and index a local database as described in the
operations runbook; seeding clears runtime rows, so never seed a database another agent uses.
Set `ANALYTICS_DATABASE_URL` to the read-only analytics login, not the schema owner.

```bash
uv run python -m agentops_retrieval benchmark \
  --git-sha "$(git rev-parse HEAD)" \
  --out retrieval-results.json
```

In PowerShell use `--git-sha (git rev-parse HEAD)`. CI may set `GITHUB_SHA` instead.
Commit code before recording a baseline so the supplied SHA names the tested implementation.
The optional `--dataset` selects a versioned judgment file; the default is
`datasets/retrieval/v1/queries.json`. Invalid cases or inaccessible relevant judgments fail
explicitly; they are not quietly counted as retrieval misses.

The command writes JSON and exits 1 if any declared forbidden document, or any document
outside the caller's actual access catalog, is returned. It exits 2 on configuration,
dataset or database errors. Low relevance scores are measurements, not a fabricated
pass/fail threshold. No benchmark artifact is written when validation fails.

## Metrics and evidence

The v1 corpus has 16 manually judged synthetic queries: 12 with accessible relevant chunks,
and four with no accessible relevant evidence (role or tenant restrictions).
Each uses k=3.

- Recall@k: unique relevant chunks retrieved within k, divided by all relevant judgments.
- Reciprocal rank: one divided by the first relevant rank within k, or zero if none.
- Mean Recall@k and MRR: macro-averages over the 12 answerable queries only.
- No-accessible-evidence queries: null relevance metrics, counted separately; not perfect
  scores. Candidate ids remain visible for inspection.
- Forbidden hits: counted independently, including for unanswerable queries.

JSON records dataset version and canonical-content SHA-256, supplied git SHA, embedding
model, per-query ids/distances/source hashes and aggregates. Retrieved text is not copied.

## Recorded v1 baseline

The [measured JSON report](../benchmarks/retrieval/v1/results.json) was generated on
2026-11-24 from implementation commit `dc644a3c766f3c3149b447ccb9ff72f09cbea2e9`,
after seeding and indexing the isolated synthetic database with `hashing-v1-256`.

| Measurement | Result |
|---|---|
| Total / answerable / no-accessible-evidence queries | 16 / 12 / 4 |
| Mean Recall@3 (answerable queries only) | 1.0 |
| MRR (answerable queries only) | 1.0 |
| Forbidden hits | 0 |

All 12 answerable queries found their judged chunk at rank one. This result is a
regression baseline on the curated seeded vocabulary, **not** a held-out quality score.
The four unanswerable/access queries remain unscored; returned candidates are not
evidence that the system can answer or abstain correctly.

## Limits

This small corpus deliberately shares vocabulary with seeded documents. It is not held-out,
real-world retrieval, semantic understanding, or end-to-end answer quality. Nearest-neighbor
search returns candidates even when none is relevant; this benchmark neither implements
nor measures abstention. Do not add reranking or a score threshold based on these cases
alone. The hash identifies the judgment dataset; source hashes identify returned chunks,
so seed/index the intended source version before comparing reports.

## Parallel lane validation

This feature is developed on `lane/feat-013` from the pre-feat-012 activation baseline.
Tests use `agentops_feat013_test`, not the other agent's database. Set all three
`AGENTOPS_TEST_DATABASE_URL`, `AGENTOPS_TEST_ANALYTICS_URL` and `AGENTOPS_TEST_APP_URL`
to that database before running integration tests or the feature gate.
Set `GITHUB_SHA` to `git rev-parse HEAD` for legacy evaluation provenance tests: their
existing fallback assumes `.git` is a directory and does not resolve worktree pointer files.
That evaluation code is intentionally not changed in this independent lane.
