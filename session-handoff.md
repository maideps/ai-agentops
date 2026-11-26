# Session Handoff

## Current Objective

- Goal: feat-016 (live evaluation scores answers) closed. No feature is active.
- Current status: feat-001 through feat-016 passing.
- Branch: main; local commits ahead of origin until the owner approves a push.

## Completed This Session

- Interactive architecture map published and added as docs/architecture-map.html; ARCHITECTURE.md corrected for feat-015 retries.
- feat-016: error codes per result; live expectations on every workflow case (evals-v1.2.0, D-018); live counts in corpus and benchmark reports.

## Verification Evidence

| Check | Result | Evidence |
|---|---|---|
| feat-016 gate | PASS, five layers | .harness/state/feat-016.json and trail |
| Regressions | npm run check exit 0; 146 offline, 128 integration, nine UI e2e | Mock corpus 50/50, mock benchmark 42/42 |
| Live corpus v1.2.0 at 52b41f8 | live outcomes 29/41; all 12 failures RATE_LIMITED | benchmarks/evals/v1.2/live/evals-live.json |
| Live benchmark at 52b41f8 | single 21/41, specialists 19/41 | benchmarks/orchestration/v1/live-evals-v1.2/ |

## Files Changed

- See progress/021-2026-11-26.md.

## Decisions

- D-018: live evaluation scores outcomes with safety invariants; mock expectations unchanged.

## Risks

- Free-tier 429s are the main live failure cause and are never retried.
- Multi-source reports sometimes cite no policy document.
- Each case runs once; small differences are noise.
- docs/architecture-map.html is a hand-maintained snapshot that stops at feat-015.
- Live runs need the owner's `.env` (unreadable to the assistant); run them from the owner's terminal with fresh cap approval.
- ./init.sh remains unusable (D-004); use uv, brief and npm check.

## Next Session Startup

1. Read AGENTS.md, docs/STANDARDS.md, the latest progress note and this handoff.
2. Run the harness brief and npm run check. No feature is active; declare the next one before starting.

## Recommended Next Step

- Declare a feature that handles rate limits in live evaluation (pacing or a bounded, budget-reserved retry honoring Retry-After) and makes reports cite a consulted policy passage; then rerun live evidence.
