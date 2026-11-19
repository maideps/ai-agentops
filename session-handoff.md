# Session Handoff

Fill this at session end for large sessions; keep it current otherwise.

## Current Objective

- Goal: start feat-001 (M0.1, keyless FastAPI skeleton).
- Current status: harness adopted (session 001); no product code; no feature active or passing.
- Branch / commit: main, initial commit pending owner approval.

## Completed This Session

- [x] Harness adopted and configured for a Python/uv product (D-001–D-003)
- [x] Milestones M0.1–M5.1 declared as feat-001–feat-009
- [x] Product forbid rules arch-101–arch-104, probed against a bad file

## Verification Evidence

| Check | Command | Result | Notes |
|---|---|---|---|
| Arch rules probe | `npm run check-arch` with a temporary bad file | arch-101–104 FAIL on the probe as intended | probe removed |
| Full check | `npm run check` | PASS (e2e, verify-all, quality SKIP: not configured yet) | also `./init.sh`: PASS, harness self-tests pass |

## Files Changed

- See `progress/001-2026-11-19.md`.

## Decisions Made

- D-001 adopt the harness; D-002 product tests in `testsuite/`; D-003 per-feature `uv run` layers.

## Blockers / Risks

- uv not installed; Docker CLI present, daemon unchecked; LICENSE (MIT) unconfirmed; CI lacks Python/uv until feat-001.

## Next Session Startup

1. Read `AGENTS.md`.
2. Read `feature_list.json`, `PROGRESS.md`, and the latest note under `progress/`.
3. Review this handoff and `docs/STANDARDS.md`.
4. Run the standard verification command before editing.

## Recommended Next Step

- Install uv, then `npm run activate -- feat-001` and write `testsuite/acceptance/feat_001/` first.
