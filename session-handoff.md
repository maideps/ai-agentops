# Session Handoff

## Current Objective

- Goal: feat-020 (offline BM25 retrieval comparison, another agent) and feat-021 (live evaluation stops when the provider quota runs out) merged on branch feat-021-quota-stop. No feature is active.
- Current status: feat-001 through feat-021 passing.
- Branch: feat-021-quota-stop with feat-020-retrieval-comparison merged, based on main c2827a3; landing on main needs owner approval. The other agent's worktree has started feat-022-publication-prep from feat-020's last commit.

## Completed

- feat-020 (session 027): benchmark-only fixed BM25 versus unchanged hashing over one read-only snapshot; v1 stays 1.0/1.0, stress Recall@3/MRR 0.7639/0.7361 → 0.8264/0.7986 with zero forbidden hits but individual regressions; no production adoption.
- feat-021 (session 028): per-day quota 429 → QUOTA_EXHAUSTED, never retried; live corpus and benchmark stop early (first QUOTA_EXHAUSTED or 3 consecutive rate-limited cases), record not-run cases and exit 1 (D-016 amendment 4).

## Verification

| Check | Result | Evidence |
|---|---|---|
| feat-020 gate | PASS, four layers at a465fa1 | .harness/state/feat-020.json and trail |
| feat-020 gate (merged tree) | PASS, all layers at 01d95cd's parent a7944ee | .harness/state/feat-020.json and trail |
| feat-021 gate (merged tree) | PASS, five layers | .harness/state/feat-021.json and trail |
| Live corpus v1.2.0 at 92ac088 (feat-019) | live outcomes 37/41; no RATE_LIMITED | benchmarks/evals/v1.2/live-feat019/evals-live.json |

## Decisions

- D-016 amendment 4: daily-quota 429s fail at once; live batches stop early with not-run cases recorded.
- feat-020 keeps production hashing; BM25 is exploratory and needs independent held-out evidence.

## Risks

- The combined live rerun (feat-018 + feat-019 + feat-021) is still pending after the 2026-11-26 quota exhaustion; create benchmarks/evals/v1.2/live-merged-018-019 before the corpus command.
- Daily-quota detection depends on the provider naming a per-day quota; the streak rule is the fallback.
- access-01 expects abstention, but a viewer's run may complete from permitted documents (no sales leak).
- BM25 regresses on some stress queries; it is not semantic retrieval or a production ranker. Its tests use only agentops_feat020_test.
- Live runs need the owner's `.env` (unreadable to the assistant); run them from the owner's terminal with fresh cap approval.
- Parallel agents allocate feature and session numbers independently; fetch origin/main before declaring the next feature.
- The architecture map is a snapshot through feat-015. ./init.sh remains unusable (D-004).

## Next Step

- Land this merge on main, then run the combined live corpus and benchmark after the quota resets and compare with 37/41.
