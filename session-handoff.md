# Session Handoff

Fill this at session end for large sessions; keep it current otherwise.

## Current Objective

- Goal: feat-006 (M2.2 Postgres checkpointing, execution registry, crash recovery, reconciliation).
- Current status: feat-001 to feat-005 passing (feat-005 at 92c0ea6); no feature active.
- Branch / commit: main.

## Completed This Session

- [x] feat-005 (M2.1) tool gateway, approval binding, sandbox ticket write, principal-bound MCP server (stdio)
- [x] D-009 recorded; arch-105 (only the gateway writes approvals/tickets)

## Verification Evidence

| Check | Command | Result | Notes |
|---|---|---|---|
| Feature gate | `npm run verify-feature -- feat-005` | PASS, 5/5 layers | trail in `.harness/trails/` |
| Full check | `npm run check` | PASS, 54 offline tests | integration: 77 tests in layer 5 |
| Mutation spot-check | hash / permission / write expiry / write principal | 1 failure each | all restored |

## Files Changed

- See `progress/006-2026-11-19.md` (feat-005) and `progress/007-2026-11-19.md` (history rewrite).

## Decisions Made

- D-009 tool gateway, approval binding, principal-bound MCP server, least-privilege app login.

## Blockers / Risks

- `./init.sh` unusable (D-004; upstream #63/#64). Docker Desktop must be running for feature layers 3 and 5. LiteLLM Gemini/Groq tokenizer download on first live call (D-005). Dev databases from before session 006 need the agentops_app roles (D-009). LICENSE unconfirmed. CI runs on GitHub (private repo maideps/ai-agentops); its actions still target the deprecated Node 20 runtime. History was rewritten in session 007 (blueprint PDF removed, single author); pre-rewrite commits may stay reachable on GitHub by SHA until its garbage collection.

## Next Session Startup

1. Read `AGENTS.md`, then `docs/STANDARDS.md` (its Session Start section replaces `./init.sh`).
2. Start Docker Desktop; `uv sync`, then `node scripts/framework-check.mjs brief`.
3. Read the latest note under `progress/` and this handoff.
4. Run `npm run check` before editing.

## Recommended Next Step

- Activate feat-006 and write the concurrent-retry and crash-after-commit tests first.
