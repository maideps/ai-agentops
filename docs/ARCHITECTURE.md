# Architecture

The full product architecture — trust boundaries, graph units, typed state, LLM gateway, MCP tool contract, execution registry, failure matrix, threat model — is specified in [`ARCHITECTURE_AND_REQUIREMENTS.md`](ARCHITECTURE_AND_REQUIREMENTS.md), which is authoritative. Coding rules are in [`STANDARDS.md`](STANDARDS.md). This page summarizes the layer model and how it is enforced in this repository.

## Product Layer Model

```
┌──────────────────────────────────────────────────────────┐
│ Presentation   apps/api (FastAPI), apps/web (Next.js)    │
├──────────────────────────────────────────────────────────┤
│ Application    packages/agents (LangGraph workflow),     │
│                packages/tools (policy + tool gateway,     │
│                MCP server), packages/evals                │
├──────────────────────────────────────────────────────────┤
│ Domain         packages/core (typed contracts, policies,  │
│                run state, ports)                          │
├──────────────────────────────────────────────────────────┤
│ Infrastructure packages/llm (mock, LiteLLM adapter),      │
│                packages/retrieval (pgvector), Postgres,   │
│                packages/telemetry (OTel, Langfuse)        │
└──────────────────────────────────────────────────────────┘
```

- Layers depend only on layers below them; infrastructure implements ports defined in `packages/core`.
- The domain layer imports no framework or provider SDK.
- Presentation never reaches infrastructure directly.
- An LLM response is never an authorization decision: every privileged tool call passes the server-side policy and tool gateway, whatever the MCP server or the model says.

These directories are created by the feature that first needs them, not up front.

## Enforced Rules

Product rules live in `.harness/arch-rules.json` (ids `arch-101` and up) and run on every `npm run check-arch`:

| Rule | What it forbids |
|---|---|
| arch-101 | Importing `litellm` outside `packages/llm/` (provider behavior stays behind the `LLMProvider` port) |
| arch-102 | Spawning processes (`subprocess`, `os.system`, `os.popen`, `os.exec*`, `os.spawn*`, asyncio subprocesses) in product code |
| arch-103 | Bare `except:` and single-line swallowed exceptions (`except …: pass`); Ruff `S110`/`BLE001`/`E722` cover the multi-line form |
| arch-104 | Provider or Langfuse API key patterns in tracked product files and config |

Add a rule whenever review catches a mistake a pattern can describe.

## Harness Boundaries

The harness contract (`.harness/manifest.json`, enforced by `npm run check-arch`) separates:

- **CORE** — harness files that ship as-is and are not edited here: `AGENTS.md`, `CLAUDE.md`, `scripts/`, `tests/` (harness self-tests), `skills/`, `templates/`, `Makefile`, `init.sh`.
- **INSTANCE** — this project's own state: `feature_list.json`, `.harness/state/`, `progress/`, `DECISIONS.md`, project docs.
- **PRODUCT-OWNED** — `productRoots` in the manifest: `apps/`, `packages/`, `testsuite/`, plus everything under `docs/` not listed as instance. New top-level product files (for example `pyproject.toml`, `docker-compose.yml`) are added to `productRoots` by the feature that creates them.

Verification entrypoints delegate to the Node runner (`scripts/framework-check.mjs`); Makefile targets and npm scripts are 1:1 mirrors.

## Worktree Lanes

Independent features can run in parallel, each in its own sibling git worktree on branch `lane/<feature-id>` (`npm run lane-suggest`, `lane-new`, `lane-list`, `lane-land`, `lane-drop`). For example, feat-002 (M0.2 data) and feat-003 (M1.1 provider port) both depend only on feat-001. Every state-changing lane step needs the owner's approval.

## Sharded Feature State

`feature_list.json` declares features and rarely changes; each feature's mutable `state` and `evidence` live in `.harness/state/<feature-id>.json`, written only by `npm run verify-feature`.
