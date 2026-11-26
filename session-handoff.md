# Session Handoff

## Current Objective

- Goal: feat-019 (live calls stay within provider rate limits) closed and merged with feat-018 (policy-aware report citations, landed by another agent). No feature is active.
- Current status: feat-001 through feat-019 passing.
- Branch: feat-019-rate-limits, merged with origin/main; landing on main needs owner approval.

## Completed

- feat-018 (other agent, session 025): report guidance to cite supporting document passages that survive the context limit; verified offline only.
- feat-019 (session 026): --min-call-interval pacing and bounded, budget-reserved 429 retries honoring Retry-After up to 60 s (D-016 amendment 3). Live corpus 37/41 (was 29/41) with no rate-limit failures.

## Verification

| Check | Result | Evidence |
|---|---|---|
| feat-019 gate | Rerun on the merged tree | .harness/state/feat-019.json and trail |
| feat-018 gate | PASS, four layers at bab2cce | progress/025-2026-11-26.md |
| Live corpus v1.2.0 at 92ac088 | live outcomes 37/41; no RATE_LIMITED | benchmarks/evals/v1.2/live-feat019/evals-live.json |
| Live benchmark at 92ac088 | single 37/41, specialists 38/41 | benchmarks/orchestration/v1/live-feat019/ |

## Decisions

- D-016 amendment 3: rate limits share the two-retry limit; Retry-After up to 60 s; optional call pacing.

## Risks

- No live run has measured feat-018's citation guidance; the feat-019 run predates it.
- access-01 expects abstention, but a viewer's run may complete from permitted documents (no sales leak).
- Retry-After above 60 s still fails a case; the 4-second interval is an estimate.
- Citation enforcement checks included ids, not semantic support.
- Live runs need the owner's `.env` (unreadable to the assistant); run them from the owner's terminal with fresh cap approval.
- Parallel agents allocate feature and session numbers independently; fetch origin/main before declaring the next feature.
- The architecture map is a snapshot through feat-015. ./init.sh remains unusable (D-004).

## Next Step

- Rerun live evidence on the merged tree (feat-018 plus feat-019, --min-call-interval 4) to measure the citation guidance, and decide whether access-01 should accept a completed report built only from permitted documents.
