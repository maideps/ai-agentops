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
│                packages/data (migrations, seed, typed     │
│                tenant-scoped reads), Postgres + pgvector, │
│                packages/retrieval, packages/telemetry     │
└──────────────────────────────────────────────────────────┘
```

- Layers depend only on layers below them; infrastructure implements ports defined in `packages/core`.
- The domain layer imports no framework or provider SDK.
- Presentation never reaches infrastructure directly.
- An LLM response is never an authorization decision: every privileged tool call passes the server-side policy and tool gateway, whatever the MCP server or the model says.

These directories are created by the feature that first needs them, not up front.

## Tool Gateway and MCP (D-009)

`packages/tools` holds the typed read tools, the `ToolGateway` and the first-party MCP server. The gateway is the only place that decides: tool allowlist, the principal's role permissions, strict arguments, and for the sandbox write an approval bound to principal, run, tool, policy version and the hash of the exact arguments, consumed in the same transaction as the write. Every decision goes to the append-only `policy_events` table. The MCP server is built per principal and run by the trusted backend and only forwards calls to the gateway.

## Orchestrations (D-012)

The default run is the single workflow. An experimental `specialists` orchestration replaces its plan/authorize/execute steps with two subgraphs, Research (document search only) and Data Analyst (sales summary only), followed by a deterministic `aggregate_evidence` step; reporting, citation policy, approvals and limits are shared. The benchmark in `benchmarks/orchestration/v1/` keeps the single workflow as the default.

## Tracing and Evaluation (D-011)

`packages/telemetry` configures OpenTelemetry with every exporter behind a redaction layer; spans carry ids, counts and codes, never prompt or document text, and share the run's trace id. The workflow reads only through the tool gateway, so role permissions and the policy log cover every tool call. `packages/evals` runs the versioned corpus in `datasets/evals/` in mock mode and records dataset version, git commit, model, prompt version and policy version.

## Recovery and Resumable Runs (D-010)

Ticket writes go through the `tool_executions` registry: the gateway reserves one execution per approval (consuming the approval in the same transaction), claims it, calls the sandbox ticket service (which commits on its own and is idempotent on the `SBX-…` reference), then records the outcome. `uncertain` and stale `executing` rows are reconciled by reference before any retry. Runs that propose a ticket pause at a LangGraph `interrupt`; their state lives in PostgreSQL checkpoints keyed by `thread-<run_id>`, and `resume_task` continues them in any process.

## First Workflow (D-008)

`packages/agents` holds one LangGraph graph: `validate_request → plan → authorize_tools → execute_tools → synthesize_report → output_policy → finalize`. The model only proposes tool calls; `agentops_agents.policy` allows or denies each one (allowlist, strict argument schema, tenant and user taken from the run) and drops report findings whose citations were not in the model's context. Limits on LLM calls, tool calls, graph steps and wall time end the run with an explicit status. `packages/retrieval` embeds chunks with a deterministic hashing embedder and searches only the documents the user may read.

## Data Isolation (D-007)

- Tenant tables use PostgreSQL row-level security keyed on `app.tenant_id`, set per transaction by the typed functions in `agentops_data.access`; with no tenant set, a query returns no rows.
- The analytics login `agentops_analytics` has `SELECT` only (through `agentops_readonly`) and cannot bypass row-level security; the schema owner `agentops` runs migrations and the seed.
- Documents are filtered by role access label (`role_document_access`); missing and forbidden documents are indistinguishable to the caller.

## Enforced Rules

Product rules live in `.harness/arch-rules.json` (ids `arch-101` and up) and run on every `npm run check-arch`:

| Rule | What it forbids |
|---|---|
| arch-101 | Importing `litellm` outside `packages/llm/` (provider behavior stays behind the `LLMProvider` port) |
| arch-102 | Spawning processes (`subprocess`, `os.system`, `os.popen`, `os.exec*`, `os.spawn*`, asyncio subprocesses) in product code |
| arch-103 | Bare `except:` and single-line swallowed exceptions (`except …: pass`); Ruff `S110`/`BLE001`/`E722` cover the multi-line form |
| arch-104 | Provider or Langfuse API key patterns in tracked product files and config |
| arch-105 | Writes to `approvals`, `tool_executions` or `sandbox_tickets` anywhere but the tool gateway and its ticket service |

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
