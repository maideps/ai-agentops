# Session Handoff

## Current Objective

- Goal: feat-019 (live calls stay within provider rate limits) closed and merged with feat-018 (policy-aware report citations). No feature is active.
- Current status: feat-001 through feat-019 passing.
- Branch: feat-019-rate-limits, merged with origin/main; landing on main needs owner approval.

## Completed This Session

- feat-019: --min-call-interval pacing and bounded, budget-reserved 429 retries honoring Retry-After up to 60 s (D-016 amendment 3).
- Live corpus 37/41 (was 29/41) with no rate-limit failures.

## Verification Evidence

| Check | Result | Evidence |
|---|---|---|
| feat-019 gate | PASS, five layers | .harness/state/feat-019.json and trail |
| Regressions | npm run check exit 0; 156 offline, 130 integration, nine UI e2e | Before the merge with feat-018 |
| Live corpus v1.2.0 at 92ac088 | live outcomes 37/41; no RATE_LIMITED | benchmarks/evals/v1.2/live-feat019/evals-live.json |
| Live benchmark at 92ac088 | single 37/41, specialists 38/41 | benchmarks/orchestration/v1/live-feat019/ |

## Files Changed

- See progress/026-2026-11-26.md; feat-018 is in progress/025-2026-11-26.md.

## Decisions

- D-016 amendment 3: rate limits share the two-retry limit; Retry-After up to 60 s; optional call pacing.

## Risks

- The feat-019 live run did not include feat-018's citation guidance; the merged tree is not yet measured live.
- access-01 expects abstention, but a viewer's run may complete from permitted documents (no sales leak).
- Retry-After above 60 s still fails a case; the 4-second interval is an estimate.
- Live runs need the owner's `.env` (unreadable to the assistant); run them from the owner's terminal with fresh cap approval.
- Parallel agents allocate feature and session numbers independently; fetch origin/main before declaring the next feature.
- ./init.sh remains unusable (D-004); use uv, brief and npm check.

## Next Session Startup

1. Read AGENTS.md, docs/STANDARDS.md, the latest progress note and this handoff.
2. Fetch origin, run the harness brief and npm run check. No feature is active; declare the next one before starting.

## Recommended Next Step

- Rerun live evidence on the merged tree (feat-018 plus feat-019, --min-call-interval 4) and decide whether access-01 should accept a completed report built only from permitted documents.
