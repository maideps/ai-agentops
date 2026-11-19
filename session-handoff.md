# Session Handoff

Fill this at session end for large sessions; keep it current otherwise.

## Current Objective

- Goal: feat-005 (M2.1 MCP server, policy gateway, approval binding, sandbox ticket write).
- Current status: feat-001 to feat-004 passing (feat-004 at 4362028); no feature active.
- Branch / commit: main.

## Completed This Session

- [x] feat-004 (M1.2) first workflow: bounded LangGraph graph, tool and citation policy, offline retrieval, recorded replay
- [x] D-008 (workflow and embedding design) recorded

## Verification Evidence

| Check | Command | Result | Notes |
|---|---|---|---|
| Feature gate | `npm run verify-feature -- feat-004` | PASS, 5/5 layers | trail in `.harness/trails/` |
| Full check | `npm run check` | PASS, 54 offline tests | integration: 46 tests in layer 5 |
| Mutation spot-check | citations / LLM budget / retrieval ACL | 4, 1 and 6+6 failures | all restored |

## Files Changed

- See `progress/005-2026-11-19.md`.

## Decisions Made

- D-008 first workflow: bounded LangGraph graph, policy-owned decisions, offline hashing embeddings.

## Blockers / Risks

- `./init.sh` unusable (D-004; upstream #63/#64). Docker Desktop must be running for feature layers 3 and 5. LiteLLM Gemini/Groq tokenizer download on first live call (D-005). LICENSE unconfirmed. CI not run yet (no remote).

## Next Session Startup

1. Read `AGENTS.md`, then `docs/STANDARDS.md` (its Session Start section replaces `./init.sh`).
2. Start Docker Desktop; `uv sync`, then `node scripts/framework-check.mjs brief`.
3. Read the latest note under `progress/` and this handoff.
4. Run `npm run check` before editing.

## Recommended Next Step

- Activate feat-005 and write the approval-binding tests (forged, expired, mutated, replayed) first.
