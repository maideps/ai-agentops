# Session Handoff

Fill this at session end for large sessions; keep it current otherwise.

## Current Objective

- Goal: feat-012 hosted-model implementation is offline-verified; the feature remains active pending an owner-approved live evidence run.
- Current status: feat-001 to feat-011 passing (feat-011 at 9f7ae40).
- Branch / commit: main.

## Completed This Session

- [x] Gemini registry/key loading, fail-closed whole-context reservations, no hidden retries.
- [x] Explicit live corpus/benchmark modes with shared command caps, cost/reservation metadata and preserved failures.
- [x] Offline acceptance including HTTP and real LangGraph/local-PostgreSQL workflows with stubbed completions.
- [x] Owner chose a verified offline checkpoint; real provider calls are not authorized.

## Verification Evidence

| Check | Command | Result | Notes |
|---|---|---|---|
| Hosted acceptance | `uv run pytest testsuite/acceptance/feat_012 -q` | PASS, 33 tests | Stubbed completions; includes local database |
| Static checks | Ruff and mypy | PASS | 107 source files |
| Full final regression | `npm run check` and integration suite | PASS | 114 offline, 121 integration, nine UI e2e; six screenshots reviewed |
| Real hosted evidence / feature gate | Manual corpus/benchmark; then `npm run verify-feature -- feat-012` | Not run | No key or approved live spend; feature stays active |

## Files Changed

- See `progress/015-2026-11-24.md` for this checkpoint; feat-011 evidence remains at 9f7ae40.

## Decisions Made

- D-016: Gemini Flash-Lite, key GEMINI_API_KEY, zero-default per-run budget and whole-context reservations. The owner explicitly approved conservative fail-closed behavior and keeping feat-012 active until a later real run.

## Blockers / Risks

- No GEMINI_API_KEY is configured; no real hosted corpus or benchmark evidence exists. Whole-context reservation is deliberately conservative and process-local; provider prices/token ceilings are assumptions, not an invoice guarantee. See D-016 and the manual procedure in docs/runbooks/operations.md. The unrelated .codewhale directory predates this work and is left untouched; its untracked lock prevents a completely clean git status and clean-check.
- `./init.sh` remains unusable (D-004); use uv/brief/check instead. Docker Desktop was started for local regressions. First real Gemini call may download a tokenizer (D-005).

## Next Session Startup

1. Read `AGENTS.md`, then `docs/STANDARDS.md` (its Session Start section replaces `./init.sh`).
2. Start Docker Desktop; `uv sync`; `node scripts/framework-check.mjs brief`. After pulling new migrations: `python -m agentops_data migrate` and `python -m agentops_agents setup-checkpoints` (owner DATABASE_URL).
3. Read the latest note under `progress/` and this handoff.
4. Run `npm run check` before editing. feat-012 is already active; do not activate another feature.

## Recommended Next Step

- Configure the key securely, obtain explicit approval for both live command caps, and collect commit-bound corpus/benchmark reports using the manual procedure. Preserve failed cases and cost metadata. Only after that run verify-feature, update README/quality/progress and commit the gate evidence. No live run is authorized by this handoff.
