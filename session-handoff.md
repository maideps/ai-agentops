# Session Handoff

Fill this at session end for large sessions; keep it current otherwise.

## Current Objective

- Goal: owner decisions pending (live model run, license, wording); no feature active.
- Current status: feat-001 to feat-011 passing (feat-011 at 9f7ae40).
- Branch / commit: main.

## Completed This Session

- [x] feat-009 (M5.1) replay-first static demo (5 replays, Playwright with no off-machine requests), capped live POST /v1/runs, threat model, runbooks, known limitations
- [x] Documented reproduction commands executed (see progress/011)

## Verification Evidence

| Check | Command | Result | Notes |
|---|---|---|---|
| Feature gate | `npm run verify-feature -- feat-009` | PASS, 5/5 layers | 6 screenshots kept as evidence |
| Full check | `npm run check` | PASS, 84 offline + 9 UI e2e | integration: 103 tests |
| Eval corpus | `python -m agentops_evals run` | 50/50 at a8b8caf | |

## Files Changed

- See `progress/013-2026-11-19.md` (feat-011) and `progress/012-2026-11-19.md` (feat-010, CI).

## Decisions Made

- D-014 tenant-isolated run checkpoints; D-015 HTTP approvals and resume; CI actions on Node 24 pinned by SHA.

## Blockers / Risks

- `./init.sh` unusable (D-004; upstream #63/#64). Docker Desktop must be running for feature layers 3 and 5. LiteLLM Gemini/Groq tokenizer download on first live call (D-005). Dev databases from before session 006 need the agentops_app roles (D-009). LICENSE resolved (MIT, `LICENSE` present). GitHub repo description still says "portfolio project" (owner action on GitHub). CI runs on GitHub (private repo maideps/ai-agentops); its actions still target the deprecated Node 20 runtime. History was rewritten in session 007 (blueprint PDF removed, single author); pre-rewrite commits may stay reachable on GitHub by SHA until its garbage collection.

## Next Session Startup

1. Read `AGENTS.md`, then `docs/STANDARDS.md` (its Session Start section replaces `./init.sh`).
2. Start Docker Desktop; `uv sync`; `node scripts/framework-check.mjs brief`. After pulling new migrations: `python -m agentops_data migrate` and `python -m agentops_agents setup-checkpoints` (owner DATABASE_URL).
3. Read the latest note under `progress/` and this handoff.
4. Run `npm run check` before editing.

## Recommended Next Step

- Owner's choice: an opted-in, budget-capped hosted-model run of the corpus and benchmark (provider, key handling and budget cap TBD); CI actions off Node 20. Add new work to feature_list.json before starting.
