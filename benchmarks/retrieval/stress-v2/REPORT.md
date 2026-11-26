# Retrieval stress comparison

Measured 2026-11-24 at corpus/code commit
`d6f0c3bace40b8cda82c39c76fd1a4f7a13e00de`. Both reports use `hashing-v1-256` on
one freshly seeded/indexed isolated PostgreSQL database: seven documents, 16 chunks.
No source, ranking or query change occurred between runs; common retrieved source
hashes match. No hosted calls or spend.

## Measured results

| Corpus | Queries | Answerable / unscored | Mean Recall@3 | MRR | Forbidden hits |
|---|---|---|---|---|---|
| [v1 control](baseline.json) | 16 | 12 / 4 | 1.0000 | 1.0000 | 0 |
| [stress v2](results.json) | 28 | 24 / 4 | 0.7639 | 0.7361 | 0 |

Each JSON records its own canonical dataset hash, the same commit/model, per-query
judgments, retrieved ids, source hashes and distances. Original v1 data/evidence
remain unchanged; baseline.json is a new paired control, not an overwrite.

| Stress family | Answerable cases | Recall@3 | MRR | Complete / partial / missed |
|---|---|---|---|---|
| Paraphrase | 8 | 0.7500 | 0.5417 | 6 / 0 / 2 |
| Multi-chunk | 8 | 0.6667 | 0.8750 | 3 / 4 / 1 |
| Distractor | 8 | 0.8750 | 0.7917 | 7 / 0 / 1 |

Complete means all judged chunks appeared within three hits; partial means some but
not all; missed means none. Four additional role/tenant negatives have null relevance
metrics and are excluded from both means. Their candidate lists and forbidden-hit
checks remain in results.json; candidates are not an answer or abstention decision.

## Incomplete retrieval

| Case | Recall@3 | Missing judged chunk(s) |
|---|---|---|
| paraphrase-unused | 0 | doc-a-returns-policy#0 |
| paraphrase-waterproof | 0 | doc-a-returns-policy#2 |
| multi-return-terms | 1/2 | doc-a-returns-policy#0 |
| multi-pricing-authority | 0 | doc-a-pricing-guidelines#0, doc-a-pricing-guidelines#1 |
| multi-stove-outlets | 2/3 | doc-a-board-notes#0 |
| multi-entry-arrivals | 1/2 | doc-b-supplier-onboarding#2 |
| multi-supplier-lifecycle | 2/3 | doc-b-supplier-policy#0 |
| distractor-return-proof | 0 | doc-a-returns-policy#1 |

The paraphrased unused-footwear question retrieves pricing and press-kit chunks instead
of its refund evidence. The waterproof-clothing paraphrase misses the seam-seal remedy.
Some successful paraphrases find evidence only at rank two or three. Four multi questions
get their first relevant chunk at rank one yet miss secondary evidence: high MRR alone
does not demonstrate completeness. A harvest-check distractor ranks entry paperwork and
the specific APAC audit event above the general seasonal policy, finding it only at rank
three. These are observed examples, not an attribution of each error to a specific
hash collision, vocabulary gap or weighting effect.

## Interpretation and reproduction

The stress set is deliberately different from v1; lower scores are not a regression in
an unchanged ranker or a causal quality comparison. Queries/judgments were manually
reviewed before the passing CLI acceptance run and never revised in response to scores.
No threshold or ranking change is justified by this report alone.

This is small, agent-curated synthetic evidence, not independent held-out/real-world
quality, semantic-understanding or end-to-end answer quality. Zero forbidden hits covers
these cases, not universal access safety. Neither corpus measures abstention.

See [judgment intent and reproduction](../../../docs/retrieval-baseline.md#stress-corpus-v2).
Run both commands against the same seeded index and committed code, using the read-only
analytics login. Record a new version/report for future query or ranking changes rather
than editing this baseline.
