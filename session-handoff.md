# Session Handoff

Fill this at session end for large sessions; keep it current otherwise.

## Current Objective

- Goal: feat-009 (M5.1 replay-first demo UI and portfolio evidence).
- Current status: feat-001 to feat-008 passing (feat-008 at faacefa); no feature active.
- Branch / commit: main.

## Completed This Session

- [x] feat-008 (M4.1) specialist subgraphs and orchestration benchmark: keep the single workflow (42/42 both, 1.81 vs 2.74 model calls)
- [x] D-012 recorded; results in benchmarks/orchestration/v1 name their code commit

## Verification Evidence

| Check | Command | Result | Notes |
|---|---|---|---|
| Feature gate | `npm run verify-feature -- feat-008` | PASS, 4/4 layers | trail in `.harness/trails/` |
| Full check | `npm run check` | PASS, 71 offline tests | integration: 101 tests |
| Benchmark | `python -m agentops_evals benchmark` | keep_single_workflow | measured fields reproducible |

## Files Changed

- See `progress/010-2026-11-19.md`.

## Decisions Made

- D-012 specialist roles stay an experiment; the single workflow remains the default.

## Blockers / Risks

- `./init.sh` unusable (D-004; upstream #63/#64). Docker Desktop must be running for feature layers 3 and 5. LiteLLM Gemini/Groq tokenizer download on first live call (D-005). Dev databases from before session 006 need the agentops_app roles (D-009). LICENSE unconfirmed. CI runs on GitHub (private repo maideps/ai-agentops); its actions still target the deprecated Node 20 runtime. History was rewritten in session 007 (blueprint PDF removed, single author); pre-rewrite commits may stay reachable on GitHub by SHA until its garbage collection.

## Next Session Startup

1. Read `AGENTS.md`, then `docs/STANDARDS.md` (its Session Start section replaces `./init.sh`).
2. Start Docker Desktop; `uv sync`; `node scripts/framework-check.mjs brief`. After pulling new migrations: `python -m agentops_data migrate` and `python -m agentops_agents setup-checkpoints` (owner DATABASE_URL).
3. Read the latest note under `progress/` and this handoff.
4. Run `npm run check` before editing.

## Recommended Next Step

- Activate feat-009: settle the replay data format (RunDetail JSON) first, then write the Playwright replay tests before the Next.js UI.
