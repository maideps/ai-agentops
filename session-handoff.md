# Session Handoff

Fill this at session end for large sessions; keep it current otherwise.

## Current Objective

- Goal: feat-007 (M3.1 observability, redaction, feedback API, evaluation corpus).
- Current status: feat-001 to feat-006 passing (feat-006 at 404b264); no feature active.
- Branch / commit: main.

## Completed This Session

- [x] feat-006 (M2.2) execution registry, crash/ambiguity recovery, Postgres checkpoints, approval pause and resume
- [x] D-010 recorded; arch-105 widened to tool_executions

## Verification Evidence

| Check | Command | Result | Notes |
|---|---|---|---|
| Feature gate | `npm run verify-feature -- feat-006` | PASS, 5/5 layers | trail in `.harness/trails/` |
| Full check | `npm run check` | PASS, 54 offline tests | integration: 88 tests in layer 5 |
| Mutation spot-check | reference lookup / lease / approval interrupt | 2, 1 and 4 failures | all restored |

## Files Changed

- See `progress/008-2026-11-19.md`.

## Decisions Made

- D-010 execution registry, external-style ticket service, Postgres checkpoints, approval pause.

## Blockers / Risks

- `./init.sh` unusable (D-004; upstream #63/#64). Docker Desktop must be running for feature layers 3 and 5. LiteLLM Gemini/Groq tokenizer download on first live call (D-005). Dev databases from before session 006 need the agentops_app roles (D-009). LICENSE unconfirmed. CI runs on GitHub (private repo maideps/ai-agentops); its actions still target the deprecated Node 20 runtime. History was rewritten in session 007 (blueprint PDF removed, single author); pre-rewrite commits may stay reachable on GitHub by SHA until its garbage collection.

## Next Session Startup

1. Read `AGENTS.md`, then `docs/STANDARDS.md` (its Session Start section replaces `./init.sh`).
2. Start Docker Desktop; `uv sync`; `node scripts/framework-check.mjs brief`. After pulling new migrations: `python -m agentops_data migrate` and `python -m agentops_agents setup-checkpoints` (owner DATABASE_URL).
3. Read the latest note under `progress/` and this handoff.
4. Run `npm run check` before editing.

## Recommended Next Step

- Activate feat-007 and write the redaction canary and evaluation-corpus tests first; consider routing the workflow's read tools through the gateway beforehand.
