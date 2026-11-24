# Session Handoff

## Current Objective

- Goal: feat-015 (hosted-call reliability) closed. No feature is active.
- Current status: feat-001 through feat-015 passing.
- Branch: main; local commits ahead of origin until the owner approves a push.

## Completed This Session

- feat-014 closed and pushed; feat-015 declared, implemented, live-run and gated.
- Bounded, budget-reserved retries for 503/connection errors; 1,024-token default output; OUTPUT_TRUNCATED; retries recorded in reports.

## Verification Evidence

| Check | Result | Evidence |
|---|---|---|
| feat-015 gate | PASS, five layers | .harness/state/feat-015.json and trail |
| Regressions | npm run check exit 0; 137 offline, 128 integration, nine UI e2e | Mock corpus and benchmark unchanged |
| Live corpus v1.1.0 at 41ea7f0 | 11/50; 22 completed workflows (was 5), 17 failed (was 33), 27 retries | benchmarks/evals/v1.1/live-feat015/evals-live.json |
| Live benchmark at 41ea7f0 | single 2/42, specialists 4/42, 45 retries | benchmarks/orchestration/v1/live-feat015/ |

## Files Changed

- See progress/020-2026-11-24.md.

## Decisions

- D-016 amendment 2: at most two budget-reserved retries for 503/connection errors; 1,024-token output; OUTPUT_TRUNCATED.

## Risks

- Corpus pass rate reflects mock-trajectory expectations, not answer quality; failed live cases' error codes are not recorded yet.
- The live benchmark's adopt_specialists comes from a two-case difference in one run: noise.
- Reservations remain process-local; provider overload beyond two retries still fails a case.
- Live runs need the owner's `.env` (unreadable to the assistant); run them from the owner's terminal with fresh cap approval.
- ./init.sh remains unusable (D-004); use uv, brief and npm check.

## Next Session Startup

1. Read AGENTS.md, docs/STANDARDS.md, the latest progress note and this handoff.
2. Run the harness brief and npm run check. No feature is active; declare the next one before starting.

## Recommended Next Step

- Declare a feature that records error codes for live cases and adds a live-mode expectation set scoring answers (correct declines, supported citations, required abstentions) rather than mock trajectories.
