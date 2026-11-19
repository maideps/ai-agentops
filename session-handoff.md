# Session Handoff

Fill this at session end for large sessions; keep it current otherwise.

## Current Objective

- Goal: feat-008 (M4.1 three-specialist comparison against the single-workflow baseline).
- Current status: feat-001 to feat-007 passing (feat-007 at 5242686); no feature active.
- Branch / commit: main.

## Completed This Session

- [x] feat-007 (M3.1) redacted tracing, feedback API, 50-case evaluation corpus (50/50 in mock mode)
- [x] Workflow reads now go through the gateway (fixed a viewer access gap); D-011 recorded

## Verification Evidence

| Check | Command | Result | Notes |
|---|---|---|---|
| Feature gate | `npm run verify-feature -- feat-007` | PASS, 5/5 layers | trail in `.harness/trails/` |
| Full check | `npm run check` | PASS, 70 offline tests | integration: 94 tests in layer 5 |
| Eval corpus | `python -m agentops_evals run` | 50/50 | mutated expectations all fail |

## Files Changed

- See `progress/009-2026-11-19.md`.

## Decisions Made

- D-011 redacted tracing, one tool path through the gateway, demo-token feedback, versioned evaluation corpus.

## Blockers / Risks

- `./init.sh` unusable (D-004; upstream #63/#64). Docker Desktop must be running for feature layers 3 and 5. LiteLLM Gemini/Groq tokenizer download on first live call (D-005). Dev databases from before session 006 need the agentops_app roles (D-009). LICENSE unconfirmed. CI runs on GitHub (private repo maideps/ai-agentops); its actions still target the deprecated Node 20 runtime. History was rewritten in session 007 (blueprint PDF removed, single author); pre-rewrite commits may stay reachable on GitHub by SHA until its garbage collection.

## Next Session Startup

1. Read `AGENTS.md`, then `docs/STANDARDS.md` (its Session Start section replaces `./init.sh`).
2. Start Docker Desktop; `uv sync`; `node scripts/framework-check.mjs brief`. After pulling new migrations: `python -m agentops_data migrate` and `python -m agentops_agents setup-checkpoints` (owner DATABASE_URL).
3. Read the latest note under `progress/` and this handoff.
4. Run `npm run check` before editing.

## Recommended Next Step

- Activate feat-008: define the specialist roles as an experiment and compare them with the baseline on the corpus before changing the default design.
