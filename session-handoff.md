# Session Handoff

Fill this at session end for large sessions; keep it current otherwise.

## Current Objective

- Goal: feat-012 (hosted-model live run) is closed with real Gemini evidence. No feature is active.
- Current status: feat-001 to feat-012 passing (feat-012 code at 48355cf, live reports committed after it).
- Branch / commit: main, local commits not yet pushed.

## Completed This Session

- [x] Diagnosed the first live attempt: provider 404, `gemini-2.5-flash-lite` withdrawn for new users.
- [x] Owner-approved switch to `gemini/gemini-3.5-flash-lite` with D-016/ADR-0016 amendment and rescaled test budgets.
- [x] Owner ran the live corpus (cap USD 79) and benchmark (cap USD 157) on the free tier; reports committed.
- [x] `npm run verify-feature -- feat-012`: all five layers PASS.

## Verification Evidence

| Check | Command | Result | Notes |
|---|---|---|---|
| Hosted acceptance | `uv run pytest testsuite/acceptance/feat_012 -q` | PASS, 33 tests | After model switch |
| Full regression | `npm run check`; integration suite | PASS | Exit 0; 121 integration |
| Live corpus | `agentops_evals run --live --budget-usd 79` | 11/50 | USD 0.0101 reported; mostly abstentions |
| Live benchmark | `agentops_evals benchmark --live --budget-usd 157` | 5/42 both | USD 0.0140 reported; keep_single_workflow |
| Feature gate | `npm run verify-feature -- feat-012` | PASS | Evidence in .harness/state/feat-012.json |

## Files Changed

- See `progress/016-2026-11-24.md`.

## Decisions Made

- D-016 amendment: allowlisted model is now `gemini/gemini-3.5-flash-lite`; reservation USD 0.3158228 per 500-output-token call.

## Blockers / Risks

- Live pass rates are not quality scores: Gemini abstains after one call in most workflow cases, and many expectations assume mock trajectories. Free-tier throttling ends cases as failed (no retries under a budget).
- Live runs need the owner's `.env` (git-ignored, unreadable to the assistant by a local deny rule): `uv run --env-file .env ...` from the owner's terminal.
- `.codewhale/` is excluded only locally through `.git/info/exclude`.
- `./init.sh` remains unusable (D-004); use uv/brief/check instead.

## Next Session Startup

1. Read `AGENTS.md`, then `docs/STANDARDS.md` (its Session Start section replaces `./init.sh`).
2. Start Docker Desktop; `uv sync`; `node scripts/framework-check.mjs brief`.
3. Read the latest note under `progress/` and this handoff.
4. Run `npm run check` before editing. No feature is active; declare the next one before starting.

## Recommended Next Step

- Declare a feature to investigate hosted-model abstention (prompt, tool schema, abstention rule) and a hosted-specific expectation set, so live runs measure answers rather than mock trajectories. Any new live run needs fresh owner approval of caps.
