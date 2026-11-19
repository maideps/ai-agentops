# Session Handoff

Fill this at session end for large sessions; keep it current otherwise.

## Current Objective

- Goal: feat-002 (M0.2 synthetic data and Postgres), the last dependency of feat-004.
- Current status: feat-001 (2e699f1) and feat-003 (c4866e3) passing; no feature active.
- Branch / commit: main.

## Completed This Session

- [x] feat-003 (M1.1) LLM port, gateway, mock and LiteLLM adapter, verified through the gate
- [x] D-005 (port shape, error codes) and D-006 (14-day dependency cooldown) recorded

## Verification Evidence

| Check | Command | Result | Notes |
|---|---|---|---|
| Feature gate | `npm run verify-feature -- feat-003` | PASS, 4/4 layers | trail in `.harness/trails/` |
| Full check | `npm run check` | PASS, 52 tests | e2e, verify-all, quality SKIP (not configured) |
| Mutation spot-check | break capability check / live opt-in | 3 and 2 tests fail | files restored |

## Files Changed

- See `progress/003-2026-11-19.md`.

## Decisions Made

- D-005 LLM port shape and error codes; D-006 dependency release cooldown.

## Blockers / Risks

- `./init.sh` unusable (D-004). Docker daemon unchecked. LiteLLM Gemini/Groq tokenizer download on first live call (D-005). LICENSE unconfirmed. CI not run yet (no remote).

## Next Session Startup

1. Read `AGENTS.md`, then `docs/STANDARDS.md` (its Session Start section replaces `./init.sh`).
2. `uv sync`, then `node scripts/framework-check.mjs brief`.
3. Read the latest note under `progress/` and this handoff.
4. Run `npm run check` before editing.

## Recommended Next Step

- Confirm the Docker daemon runs, then activate feat-002 and write its integration tests first.
