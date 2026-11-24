# Session Handoff

## Current Objective

- Goal: feat-014 closed; feat-015 (hosted-call reliability) is the next feature.
- Current status: feat-001 through feat-014 passing.
- Branch: main (feat-014-quarter-context merged locally; push pending owner approval).

## Completed This Session

- Diagnosed live abstentions: the plan call invented 2023–2024 quarters for 2026-only data.
- feat-014: tenant quarters in planning prompts, both-or-neither sales quarters with a two-most-recent default, corpus evals-v1.1.0 naming each task's period (D-017).
- Owner-run live corpus/benchmark on evals-v1.1.0; verify-feature feat-014 PASS.

## Verification Evidence

| Check | Result | Evidence |
|---|---|---|
| feat-014 gate | PASS, five layers | .harness/state/feat-014.json and trail |
| Regressions | npm run check exit 0; 128 offline, 128 integration, nine UI e2e | Mock corpus 50/50, mock benchmark 42/42 |
| Live corpus v1.1.0 | 11/50; 2 abstentions (was 36); 30/42 reach report call; 5 complete | benchmarks/evals/v1.1/live/evals-live.json |
| Live benchmark v1.1.0 | single 4/42, specialists 2/42 | benchmarks/orchestration/v1/live-evals-v1.1/ |
| Report diagnostic | one 503 "high demand", one truncated at 500 tokens, one complete | progress/019-2026-11-24.md |

## Files Changed

- See progress/019-2026-11-24.md.

## Decisions

- D-017: planning states the tenant's quarters; sales quarters both-or-neither; corpus v1.1.0 tasks name their period.

## Risks

- Most live report calls failed with no usage (provider 503s, network outages) and budgeted calls cannot retry (D-016).
- MAX_OUTPUT_TOKENS=500 truncates some real reports, which then fail JSON validation.
- Live pass rates remain partly bound to mock trajectories; they are not quality scores.
- Live runs need the owner's `.env` (unreadable to the assistant); run them from the owner's terminal.
- ./init.sh remains unusable (D-004); use uv, brief and npm check.

## Next Session Startup

1. Read AGENTS.md, docs/STANDARDS.md, the latest progress note and this handoff.
2. Run the harness brief and npm run check.
3. Work on feat-015 only; any new live run needs fresh owner approval of caps.

## Recommended Next Step

- feat-015: raise the report output limit, add a bounded retry for transient provider errors that reserves budget for every attempt (D-016 amendment), then rerun live evidence at a quieter time.
