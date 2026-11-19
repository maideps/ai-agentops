# Session Handoff

Fill this at session end for large sessions; keep it current otherwise.

## Current Objective

- Goal: feat-004 (M1.2 first vertical-slice graph); all its dependencies pass.
- Current status: feat-001 (2e699f1), feat-002 (355a7d0) and feat-003 (c4866e3) passing; no feature active.
- Branch / commit: main.

## Completed This Session

- [x] feat-002 (M0.2) Postgres + pgvector, synthetic tenants, RLS, read-only analytics login, verified through the gate
- [x] D-007 (tenant isolation design) recorded; harness issues #63–#68 filed upstream

## Verification Evidence

| Check | Command | Result | Notes |
|---|---|---|---|
| Feature gate | `npm run verify-feature -- feat-002` | PASS, 5/5 layers | trail in `.harness/trails/` |
| Full check | `npm run check` | PASS, 53 offline tests | integration: 30 tests in layer 5 |
| Mutation spot-check | RLS off / INSERT granted / role filter removed | 2, 1 and 3 tests fail | all restored |

## Files Changed

- See `progress/004-2026-11-19.md`.

## Decisions Made

- D-007 tenant isolation with row-level security, read-only login and typed reads.

## Blockers / Risks

- `./init.sh` unusable (D-004; upstream #63/#64). Docker Desktop must be running for feature layers 3 and 5. LiteLLM Gemini/Groq tokenizer download on first live call (D-005). LICENSE unconfirmed. CI not run yet (no remote).

## Next Session Startup

1. Read `AGENTS.md`, then `docs/STANDARDS.md` (its Session Start section replaces `./init.sh`).
2. Start Docker Desktop; `uv sync`, then `node scripts/framework-check.mjs brief`.
3. Read the latest note under `progress/` and this handoff.
4. Run `npm run check` before editing.

## Recommended Next Step

- Choose an offline embedding approach for retrieval, then activate feat-004 and write its deterministic end-to-end acceptance test first.
