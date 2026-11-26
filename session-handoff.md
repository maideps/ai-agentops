# Session Handoff

## Current Objective

- Goal: feat-020 offline BM25 comparison, developed independently of live reliability/reporting.
- Current status: feat-001 through feat-019 passing; feat-020's initial gate passed and its final deduplicated four-layer gate is pending.
- Branch: feat-020-retrieval-comparison in the owned sibling worktree, based on main c2827a3. Local only; publication needs separate owner approval.

## Completed

- feat-018 (other agent, session 025): report guidance to cite supporting document passages that survive the context limit; verified offline only.
- feat-019 (session 026): --min-call-interval pacing and bounded, budget-reserved 429 retries honoring Retry-After up to 60 s (D-016 amendment 3). Live corpus 37/41 (was 29/41) with no rate-limit failures.
- feat-020 (session 027): benchmark-only fixed BM25 versus unchanged hashing, one
  read-only repeatable-read snapshot and caller-permitted corpus statistics.
  v1 stays 1.0/1.0; stress Recall@3/MRR rises from 0.7639/0.7361 to
  0.8264/0.7986, with zero forbidden hits but individual regressions.
  No production adoption, source/judgment changes, hosted calls or spend.

## Verification

| Check | Result | Evidence |
|---|---|---|
| feat-019 gate | Rerun on the merged tree | .harness/state/feat-019.json and trail |
| feat-018 gate | PASS, four layers at bab2cce | progress/025-2026-11-26.md |
| Live corpus v1.2.0 at 92ac088 | live outcomes 37/41; no RATE_LIMITED | benchmarks/evals/v1.2/live-feat019/evals-live.json |
| Live benchmark at 92ac088 | single 37/41, specialists 38/41 | benchmarks/orchestration/v1/live-feat019/ |
| feat-020 implementation/evidence | 2268b1d / de95e52 | benchmarks/retrieval/bm25-v1/ |
| feat-020 checks | 167 offline, 136 isolated integration, nine UI; mypy 117 sources | progress/027-2026-11-26.md |
| feat-020 final gate | Pending after removing repeated default layers | .harness/state/feat-020.json |

## Decisions

- D-016 amendment 3: rate limits share the two-retry limit; Retry-After up to 60 s; optional call pacing.
- feat-020 keeps production hashing unchanged. BM25 is exploratory; no tuning or
  adoption on the inspected synthetic corpora. Independent held-out evidence is required.

## Risks

- No live run has measured feat-018's citation guidance; the feat-019 run predates it.
- access-01 expects abstention, but a viewer's run may complete from permitted documents (no sales leak).
- Retry-After above 60 s still fails a case; the 4-second interval is an estimate.
- Citation enforcement checks included ids, not semantic support.
- Live runs need the owner's `.env` (unreadable to the assistant); run them from the owner's terminal with fresh cap approval.
- Parallel agents allocate feature and session numbers independently; fetch origin/main before declaring the next feature.
- The architecture map is a snapshot through feat-015. ./init.sh remains unusable (D-004).
- BM25 loses recall on paraphrase-cooking and multi-audit-duration despite higher
  aggregate stress metrics. It is not semantic retrieval, abstention, measured
  end-to-end report quality, or a scalable production ranker.
- Comparison tests use only agentops_feat020_test. Never seed the original checkout's database.

## Next Step

- Finish the four-layer feat-020 gate and final clean-check, persist bound evidence
  and handoff, then await publication approval. Fetch main before publication to
  detect concurrent feature/session id collisions; do not modify the other agent's checkout.
- The other agent owns any newly authorized live work (feat-018 plus feat-019);
  this experiment neither reruns it nor changes access-01's expectation.
