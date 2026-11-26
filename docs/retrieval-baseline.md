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

## Stress corpus v2

feat-016 adds `datasets/retrieval/stress-v2/queries.json`, version
`retrieval-stress-v2.0.0`, without changing the embedder, ranking, source documents,
default corpus or scoring. All 28 cases use k=3. Their questions are distinct from v1.

| Family (case-id prefix) | Cases | Judgment intent |
|---|---|---|
| paraphrase | 8 | Restate eight questions with less direct vocabulary; unused/worn footwear share one source paragraph |
| multi | 8 | Require two or three relevant chunks, sometimes across documents |
| distractor | 8 | Include plausible competing topics; judge evidence answering the question, not every mentioned topic |
| no-evidence | 4 | Role/tenant restrictions leave no accessible positive judgment; scores remain null |

Judgments were read against the seven existing synthetic source documents before the
passing CLI acceptance run. They were not changed after viewing scores. The multi
questions cover remedy/pricing, footwear/refund documentation, discount/price exceptions,
company/returns, stove pricing/board reconsideration, audit/duration, supplier entry/delays
and the supplier lifecycle. The board case requires an administrator. The company/returns
case needs both public and internal evidence; a viewer can read only part of its judgment,
so the acceptance test confirms that invalid role change fails instead of becoming a miss.

For distractors, explicit background exclusions are not extra positive judgments. For
example, the harvest-check question mentions vendor-entry forms and late-delivery review,
but asks only for the seasonal qualification. The current lexical ranker does not
understand negation; competing words may therefore outrank the intended source.

Seed/index one isolated database once, then run both corpora with the same committed SHA,
read-only analytics connection and unchanged index:

```bash
uv run python -m agentops_retrieval benchmark \
  --git-sha "$(git rev-parse HEAD)" \
  --out benchmarks/retrieval/stress-v2/baseline.json
uv run python -m agentops_retrieval benchmark \
  --dataset datasets/retrieval/stress-v2/queries.json \
  --git-sha "$(git rev-parse HEAD)" \
  --out benchmarks/retrieval/stress-v2/results.json
```

In PowerShell use `--git-sha (git rev-parse HEAD)` on one line per command.
Development tests use the separate `agentops_feat015_test` database for all three
`AGENTOPS_TEST_*` URLs, plus actual `GITHUB_SHA` for legacy worktree provenance.
No hosted call is needed. Do not seed another agent's database.

The [paired comparison](../benchmarks/retrieval/stress-v2/REPORT.md) was recorded at
corpus/code commit `d6f0c3bace40b8cda82c39c76fd1a4f7a13e00de`: v1 Recall@3/MRR
1.0/1.0; stress Recall@3 0.7639, MRR 0.7361; zero forbidden hits in both. Four stress
answerable cases miss completely and four retrieve only part of the required evidence.
The queries and judgments were not changed after seeing these results.

Mean Recall@3 and
MRR still exclude the four access-negative queries; MRR can hide missing secondary chunks,
so inspect per-query Recall for multi questions. Unequal corpora have different task
distributions: a score difference is not a ranking regression or a causal quality gain.
These agent-curated synthetic judgments are not independent held-out or real-world data,
and neither report measures abstention. Do not tune ranking or a threshold on these cases.

## Offline BM25 comparison

feat-020 adds `compare`, a benchmark-only alternative to `benchmark`. Production
`search_documents`, the hashing embedder, frozen datasets and historical reports are
unchanged. One generic BM25 candidate is fixed before recording measurements:
`k1=1.2`, `b=0.75`, with the existing `tokens` function (lower-case alphanumeric
words, stopword removal, simple trailing-plural stripping). Unique query terms
contribute once; there is no query expansion, synonym list or parameter search.

For each query, BM25 scores **all and only** the caller-permitted chunks. Document
frequencies, N and average chunk length are computed from that same permitted catalog,
so inaccessible chunks cannot influence candidate statistics. For term t:
`idf(t) = ln(1 + (N - df(t) + 0.5) / (df(t) + 0.5))`; each term contributes
`idf(t) * tf(t) * (k1 + 1) / (tf(t) + k1 * (1 - b + b * length / average_length))`.
Larger scores rank first, tied by chunk id. Zero-overlap candidates are retained;
an empty catalog returns no candidates. Neither is an abstention decision.

The unchanged vector baseline and BM25 execute in one repeatable-read, read-only
transaction through the analytics login. Invalid/inaccessible relevance judgments
fail before a report is written. JSON embeds the existing baseline report and pairs
candidate results by case id, sharing metric definitions and answerable-query
denominators. BM25 `score` is separate from the baseline's cosine `distance`.
Every candidate result fingerprints the full permitted catalog as SHA-256 of UTF-8
compact JSON containing sorted `[chunk_id, text_sha256]` pairs. No retrieved text is
written; dataset version/hash and supplied git SHA remain in the baseline report.
Exit codes match `benchmark`: 0 successful measurement, 1 any forbidden hit in either
ranker, 2 configuration/dataset/database/output errors. Low relevance is not a fake
pass/fail threshold.

Seed and index one **isolated** database as above, commit the implementation, then
use the analytics login for both frozen corpora. In PowerShell:

```powershell
uv run python -m agentops_retrieval compare --git-sha (git rev-parse HEAD) --out benchmarks/retrieval/bm25-v1/control.json
uv run python -m agentops_retrieval compare --dataset datasets/retrieval/stress-v2/queries.json --git-sha (git rev-parse HEAD) --out benchmarks/retrieval/bm25-v1/stress.json
```

Tests use `agentops_feat020_test` for all three `AGENTOPS_TEST_*` URLs, not a shared
database. No model calls, downloads, new dependencies or paid inference are needed.
Report per-query regressions as well as improvements before considering next steps.
These corpora are tiny, agent-curated and already inspected: do not tune parameters,
claim semantic/end-to-end quality or adopt a production ranker from this comparison.
A production decision needs separately approved, independently judged held-out evidence.

The [recorded comparison](../benchmarks/retrieval/bm25-v1/REPORT.md) at `2268b1d`
preserves v1 Recall@3/MRR at 1.0/1.0 and measures stress BM25 at 0.8264/0.7986
against hashing at 0.7639/0.7361, with zero forbidden hits. Recall regresses on
`paraphrase-cooking` and `multi-audit-duration`; rank-only regressions are also
listed. Production adoption is explicitly deferred, not inferred from better averages.
