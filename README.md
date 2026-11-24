# AI AgentOps

A provider-agnostic, security-first agentic AI platform. It analyzes synthetic sales data, retrieves permission-filtered evidence, writes cited reports and proposes follow-up actions that run only after human approval, exactly once. It runs mock-first, with no paid model calls by default.

## Table of Contents

- [Status](#status)
- [Quick Start](#quick-start)
- [Usage](#usage)
- [Roadmap](#roadmap)
- [Documentation](#documentation)
- [License](#license)

## Status

Phase 1 complete (M0.1 to M5.1: feat-001 to feat-009). What works today:

- A FastAPI service with two endpoints: GET /health/live returns `{"status": "ok"}` and GET /health/ready returns `{"status": "ready", "checks": {}}` (no dependencies yet).
- Settings from environment variables with `LLM_MODE=mock` and `ENABLE_LIVE_LLM=false` by default; `hosted_free`/`live_paid` refuse to start without `ENABLE_LIVE_LLM=true`. Provider keys in the environment never switch the mode.
- JSON logs for the app's own events (uvicorn's access log is still plain text).
- A keyless, offline test suite: tests cannot open non-loopback connections or DNS lookups.
- A provider-independent model layer (feat-003, M1.1), used from Python; nothing in the HTTP API calls it yet:
  - `agentops_core.llm`: typed `ModelRequest`/`ModelResponse`, the `LLMProvider` port, a capability registry that rejects unknown models, and `LLMGateway`, which refuses a request needing tool calling, structured output or streaming the model lacks (`MODEL_CAPABILITY_UNSUPPORTED`) before any provider call, and validates structured output against its JSON Schema.
  - `agentops_llm.mock.MockLLMProvider`: deterministic replies scripted per run id, loadable from JSON files, zero cost.
  - `agentops_llm.litellm_provider.LiteLLMProvider`: LiteLLM SDK adapter that normalizes text, tool calls, usage and errors (`RATE_LIMITED`, `AUTH_FAILED`, `TIMEOUT`, `CAPABILITY_UNSUPPORTED`, `PROVIDER_UNAVAILABLE`, `BUDGET_EXCEEDED`, `INVALID_REQUEST`, `INVALID_RESPONSE`). Its capability registry holds no live models yet, so no live call is possible without registering one.
  - `agentops_llm.selection.select_provider`: mock by default, replay refuses every model call, and hosted or paid modes need `ENABLE_LIVE_LLM=true`.

- Synthetic data in PostgreSQL 17 + pgvector (feat-002, M0.2), from `datasets/synthetic/`: two tenants (`demo-a`, `demo-b`), four users with viewer/analyst/admin roles, 64 quarterly sales rows and seven documents split into 16 citable chunks (`<document-id>#<n>`).
  - Row-level security keeps each tenant's rows invisible to the other; the read-only analytics login cannot insert, update, delete, truncate, alter or drop anything.
  - Typed reads in `agentops_data.access`: `revenue_by_quarter`, `quarterly_sales`, `documents_for_user` and `document_chunks`, filtered by the user's role (viewer sees public documents, analyst public and internal, admin everything).
  - GET /health/ready checks the database when `DATABASE_URL` is set and answers 503 `not_ready` when it is unreachable.

- The first end-to-end workflow (feat-004, M1.2), run from the command line in mock mode: one LangGraph graph takes the sample task, plans tool calls with the scripted mock model, lets policy allow or deny each call, reads the sales declines and the documents the user may see, and returns a JSON run detail with a cited report.
  - For `demo-a`'s analyst it reports the three largest 2026-Q2→Q3 declines (Trail Running Shoes EMEA −4,000, Rain Jacket NA −3,000, Camping Stove NA −2,000), citing sales records and policy passages.
  - The run detail records each policy decision: a non-allowlisted tool, a tool call carrying another tenant's id, and a finding that cites a restricted document are all denied.
  - It abstains when the requested quarters have no data, and ends with an explicit status when an LLM-call, tool-call, step or time limit is reached.
  - Document retrieval uses a deterministic offline embedding (word hashing), so runs are reproducible; the sample run is recorded in `fixtures/replays/`.

- A first-party MCP server and tool gateway (feat-005, M2.1): `get_sales_summary`, `search_approved_documents`, `get_issue_details` and the sandbox write `create_followup_ticket`, served over stdio by `python -m agentops_tools serve` for one principal and run.
  - The gateway checks every call: allowlisted tool, the user's role permissions (a viewer cannot read sales), strict arguments with no tenant or user fields, and records each decision in an append-only policy log.
  - A ticket is written only with an approval of that exact ticket by the same user for the same run, under the current policy version and before it expires (15 minutes); the approval is used up by the write. Forged, pending, rejected, expired, changed, replayed or borrowed approvals write nothing.
  - A synthetic `demo-b` document contains a prompt-injection payload; it is returned as ordinary data, and the actions it asks for are refused.

- Recovery and resumable runs (feat-006, M2.2):
  - Every ticket write goes through an execution registry (reserved, executing, then succeeded, failed or uncertain). Concurrent retries of one approval, a crash right after the ticket service commits, and a lost response before or after the commit all end with exactly one ticket; `python -m agentops_tools recover --tenant demo-a` reconciles stuck writes by their ticket reference before retrying. This holds for the sandbox ticket service, which is idempotent on that reference; it is not a universal exactly-once guarantee.
  - A run started with `propose_followup` proposes one follow-up ticket for the largest decline, requests an approval and pauses (`awaiting_approval`). Its state is checkpointed in PostgreSQL, so it can be resumed after a restart; it writes the ticket only if the approval was granted through the gateway, and does not repeat any model or tool call.

- Observability, feedback and evaluation (feat-007, M3.1):
  - OpenTelemetry spans for the API, each run step, model calls, policy checks, tool calls, retrieval and evaluation cases, all under the run's trace id. Spans carry ids and counts only, and every exporter passes a redaction layer (keys, tokens, URL passwords, e-mail addresses). Export to Langfuse is opt-in (`LANGFUSE_ENABLED=true` plus `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY`).
  - The workflow's reads now go through the tool gateway too, so role permissions apply to them (a viewer cannot read sales) and every tool call is in the policy log.
  - POST /v1/runs/{run_id}/feedback stores a thumbs up or down, with an optional comment and evaluation-case id, for the configured demo user (bearer `DEMO_API_TOKEN`); `python -m agentops_data export-feedback --tenant demo-a` exports it.
  - A versioned 50-case evaluation corpus (`datasets/evals/v1`) covering normal, multi-source, missing-evidence, tool-misuse, prompt-injection, access, reliability and budget cases; `python -m agentops_evals run` runs it in mock mode and reports dataset version, git commit, model, prompt version and a trace id per case. All 50 pass. It scores the platform's enforcement with scripted model replies, not model quality.

- An orchestration experiment (feat-008, M4.1): Research, Data Analyst and Reporting roles as LangGraph subgraphs (`orchestration="specialists"`), each limited to its own tool. `python -m agentops_evals benchmark` runs the 42 workflow cases of the evaluation corpus under both designs and writes `benchmarks/orchestration/v1/` (results JSON and `REPORT.md`). In mock mode both reach 42/42 expected outcomes and the specialists need about one more model call per run (2.74 vs 1.81), so the single workflow stays the default. Mock mode cannot compare answer quality; no hosted-model numbers exist yet.

- A replay-first demo UI (feat-009, M5.1) in `apps/web`: a static Next.js site that shows five recorded synthetic runs (the cited sample, a viewer denied by policy, missing data, a prompt injection, and a ticket written after human approval) with their report, evidence, policy decisions, approval and trace id. It makes no request to any backend or model provider. Replays are recorded with `python -m agentops_evals record-replays` into `fixtures/replays/`.
- An optional live mode on the API: POST /v1/runs runs a task for the demo user (bearer `DEMO_API_TOKEN`), capped at `MAX_REQUESTS_PER_DEMO_USER` runs per day. In mock mode it uses a named scripted-reply file from `fixtures/llm/`.

- Tenant-isolated run checkpoints (feat-010): a paused run's saved state carries its tenant in the thread id (`<tenant>/thread-<run_id>`) and is protected by row-level security, so another tenant can neither read nor resume it.

- Approvals over HTTP (feat-011): POST /v1/runs with `"propose_followup": true` returns `awaiting_approval` and the bound proposal; POST /v1/runs/{run_id}/approvals/{approval_id} with `{"decision": "approve"}` or `"reject"` records the decision and resumes the run (one ticket at most; a second decision is 409, another user 403, another tenant 404); GET /v1/runs/{run_id} returns the run's current detail.

- A read-only retrieval benchmark (feat-013): 16 versioned synthetic queries measure the existing hashing/pgvector search. Recall@k and MRR cover the 12 queries with accessible relevant chunks; four no-accessible-evidence queries are reported separately, not given perfect scores. Reports contain chunk ids/hashes, model and commit provenance, and forbidden-hit counts, never retrieved text. Ranking is unchanged and no model is called. The [recorded synthetic baseline](benchmarks/retrieval/v1/results.json) has Recall@3 1.0, MRR 1.0 and zero forbidden hits; this is not held-out retrieval quality. See the [procedure and limitations](docs/retrieval-baseline.md).

There is no endpoint to list runs, and the UI has no live mode or approval screen. See [`docs/known-limitations.md`](docs/known-limitations.md).

## Quick Start

Prerequisites: Python 3.13, [uv](https://docs.astral.sh/uv/), Docker, Node.js ≥ 18 (development harness and the demo UI) and Git.

```bash
uv sync                                                    # install dependencies into .venv
docker compose up -d --wait postgres                       # PostgreSQL + pgvector on 127.0.0.1:15432
export DATABASE_URL=postgresql://agentops:change-me@127.0.0.1:15432/agentops
uv run python -m agentops_data migrate                     # create the schema
uv run python -m agentops_data seed                        # load datasets/synthetic
uv run python -m agentops_retrieval index                  # embed chunks (after every seed)
uv run python -m agentops_agents setup-checkpoints         # run checkpoint tables (schema owner)
export ANALYTICS_DATABASE_URL=postgresql://agentops_analytics:change-me-analytics@127.0.0.1:15432/agentops
uv run python -m agentops_agents run --run-id run-sample-q3-declines --tenant demo-a --user user-a-analyst "Analyze quarterly sales and explain the three largest declines"
export APP_DATABASE_URL=postgresql://agentops_app:change-me-app@127.0.0.1:15432/agentops
uv run python -m agentops_tools serve --tenant demo-a --user user-a-analyst --run-id run-1   # MCP over stdio
uv run python -m agentops_evals run --out evals-report.json   # 50-case evaluation, mock mode
uv run uvicorn agentops_api.app:create_app --factory       # serve the API on http://127.0.0.1:8000
curl http://127.0.0.1:8000/health/ready
npm run check                                              # lint, types, offline tests, harness checks
uv run pytest testsuite -q -m integration                  # tests against the local database
```

The compose file uses throwaway local passwords (`POSTGRES_PASSWORD`, `ANALYTICS_DB_PASSWORD`, `APP_DB_PASSWORD` override them). Database roles are created only when the data volume is first created; after changing `infra/postgres/init/`, recreate it with `docker compose down -v`.

Settings come from environment variables only; copy `.env.example` to `.env` and pass it with `--env-file .env` to use a file. Do not run `./init.sh` yet: it would install into the system Python (D-004 in `DECISIONS.md`).

## Usage

Development follows the harness loop in [`AGENTS.md`](AGENTS.md): pick the next feature, activate it, implement it, commit, then verify it through the gate.

```bash
npm run activate -- feat-001
npm run verify-feature -- feat-001
npm run lane-suggest       # which planned features could run in parallel
```

## Reproduce the key tests

```bash
docker compose up -d --wait postgres
uv sync
npm ci --prefix apps/web && npx --prefix apps/web playwright install chromium
npm run check                                              # lint, types, offline tests, harness checks, replay UI e2e
uv run pytest testsuite -q -m integration                  # tenant isolation, approvals, crash recovery, checkpoints
uv run python -m agentops_evals run                        # needs ANALYTICS_DATABASE_URL and APP_DATABASE_URL
uv run python -m agentops_evals benchmark                  # single workflow vs specialists
uv run python -m agentops_retrieval benchmark --git-sha "$(git rev-parse HEAD)" --out retrieval-results.json
npm --prefix apps/web run e2e                              # replay UI only: screenshots in apps/web/test-results/shots
```

For the demo UI alone, nothing but Node is needed: `npm ci --prefix apps/web`, `npm --prefix apps/web run build`, `npm --prefix apps/web run serve`, then open http://127.0.0.1:4173/.

Further reading: [threat model](docs/threat-model.md), [deployment checklist](docs/runbooks/deployment-checklist.md), [operations runbook](docs/runbooks/operations.md), [known limitations](docs/known-limitations.md).

## Roadmap

Features are declared in [`feature_list.json`](feature_list.json); their state is in `.harness/state/` and summarized in [`PROGRESS.md`](PROGRESS.md).

| Feature | Milestone | Slice |
|---|---|---|
| feat-001 | M0.1 | Keyless FastAPI skeleton, health endpoints, settings, logging, Ruff, mypy, pytest, CI |
| feat-002 | M0.2 | PostgreSQL + pgvector, migrations, two synthetic tenants, read-only role |
| feat-003 | M1.1 | `LLMProvider` port, mock provider, LiteLLM adapter, capability registry |
| feat-004 | M1.2 | First LangGraph workflow: SQL + retrieval → cited report, abstention |
| feat-005 | M2.1 | First-party MCP server, policy gateway, approval binding, sandbox ticket |
| feat-006 | M2.2 | Postgres checkpointing, execution registry, crash recovery, reconciliation |
| feat-007 | M3.1 | Sanitized telemetry, feedback API, 50-case evaluation corpus |
| feat-008 | M4.1 | Three-specialist comparison against the single-workflow baseline |
| feat-009 | M5.1 | Replay-first Next.js demo and portfolio evidence |
| feat-013 | Phase 2 | Read-only retrieval-relevance baseline, independent of hosted-model support |

## Documentation

- [Requirements and architecture (authoritative)](docs/ARCHITECTURE_AND_REQUIREMENTS.md)
- [Engineering handoff and milestones](docs/CLAUDE_CODE_HANDOFF.md)
- [Project standards and non-negotiable rules](docs/STANDARDS.md)
- [Product overview](docs/PRODUCT.md)
- [Architecture summary and enforced rules](docs/ARCHITECTURE.md)
- [Decisions](DECISIONS.md)
- [Harness usage guide](docs/USAGE.md)
- [Harness command reference](docs/HARNESS.md)

## License

MIT, see [`LICENSE`](LICENSE).
