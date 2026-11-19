# Session Handoff

Fill this at session end for large sessions; keep it current otherwise.

## Current Objective

- Goal: next feature after feat-001: feat-002 (M0.2 Postgres) or feat-003 (M1.1 provider port), which can run in parallel.
- Current status: feat-001 passing (evidence at commit 2e699f1); no feature active.
- Branch / commit: main.

## Completed This Session

- [x] feat-001 (M0.1) keyless FastAPI skeleton, verified through the gate
- [x] uv installed; CI switched to uv
- [x] D-004 recorded: do not run ./init.sh or npm run setup

## Verification Evidence

| Check | Command | Result | Notes |
|---|---|---|---|
| Feature gate | `npm run verify-feature -- feat-001` | PASS, 4/4 layers | trail in `.harness/trails/` |
| Full check | `npm run check` | PASS | e2e, verify-all, quality SKIP (not configured) |
| Real server | uvicorn on port 8765 + curl | both health endpoints OK | |

## Files Changed

- See `progress/002-2026-11-19.md`.

## Decisions Made

- D-003 updated (layer 1 calls harness checks directly); D-004 added (avoid init.sh/setup until the harness supports uv).

## Blockers / Risks

- `./init.sh` unusable (D-004). Docker daemon unchecked. LICENSE unconfirmed. CI not run yet (no remote).

## Next Session Startup

1. Read `AGENTS.md`, then `docs/STANDARDS.md` (its Session Start section replaces `./init.sh`).
2. `uv sync`, then `node scripts/framework-check.mjs brief`.
3. Read the latest note under `progress/` and this handoff.
4. Run `npm run check` before editing.

## Recommended Next Step

- Decide whether to fix uv support in the framework first; otherwise activate feat-002 or feat-003 and write its acceptance tests first.
