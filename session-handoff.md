# Session Handoff

## Current Objective

- Goal: feat-017 (live evaluation scores answers) closed on main after merging the other agent's feat-016 (retrieval stress). No feature is active.
- Current status: feat-001 through feat-017 passing.
- Branch: main; local commits ahead of origin until the owner approves a push. Backup of the pre-merge work: branch backup/live-scoring-before-merge (39f8816).

## Completed This Session

- Interactive architecture map published and added as docs/architecture-map.html; ARCHITECTURE.md corrected for feat-015 retries.
- feat-017 (developed as feat-016): error codes per result; live expectations on every workflow case (evals-v1.2.0, D-018); live counts in corpus and benchmark reports.
- Merged origin/main (retrieval stress feat-016, sessions 021–023) instead of rebasing, so the measured commit 52b41f8 stays in history; renumbered this work to feat-017 and session 024.

## Verification Evidence

| Check | Result | Evidence |
|---|---|---|
| feat-017 gate | Rerun on the merged tree | .harness/state/feat-017.json and trail |
| Live corpus v1.2.0 at 52b41f8 | live outcomes 29/41; all 12 failures RATE_LIMITED | benchmarks/evals/v1.2/live/evals-live.json |
| Live benchmark at 52b41f8 | single 21/41, specialists 19/41 | benchmarks/orchestration/v1/live-evals-v1.2/ |
| feat-016 retrieval stress | Landed by the other agent; gate at 084e0c6 | progress/021-2026-11-24.md to 023-2026-11-26.md |

## Files Changed

- See progress/024-2026-11-26.md (this work) and progress/021–023 (retrieval stress).

## Decisions

- D-018: live evaluation scores outcomes with safety invariants; mock expectations unchanged.

## Risks

- Free-tier 429s are the main live failure cause and are never retried.
- Multi-source reports sometimes cite no policy document.
- Each case runs once; small differences are noise.
- docs/architecture-map.html is a hand-maintained snapshot that stops at feat-015.
- Live runs need the owner's `.env` (unreadable to the assistant); run them from the owner's terminal with fresh cap approval.
- Parallel agents allocate feature and session numbers independently; fetch origin/main before declaring the next feature.
- ./init.sh remains unusable (D-004); use uv, brief and npm check.

## Next Session Startup

1. Read AGENTS.md, docs/STANDARDS.md, the latest progress note and this handoff.
2. Fetch origin, run the harness brief and npm run check. No feature is active; declare the next one before starting.

## Recommended Next Step

- Declare a feature that handles rate limits in live evaluation (pacing or a bounded, budget-reserved retry honoring Retry-After) and makes reports cite a consulted policy passage; then rerun live evidence.
