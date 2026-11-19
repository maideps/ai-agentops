# AI AgentOps

A provider-agnostic, security-first agentic AI platform (portfolio project). It analyzes synthetic sales data, retrieves permission-filtered evidence, writes cited reports and proposes follow-up actions that run only after human approval, exactly once. It runs mock-first, with no paid model calls by default.

## Table of Contents

- [Status](#status)
- [Quick Start](#quick-start)
- [Usage](#usage)
- [Roadmap](#roadmap)
- [Documentation](#documentation)
- [License](#license)

## Status

Early stage (M0.1 to M2.2 done: feat-001 to feat-006). What works today:

- A FastAPI service with two endpoints: GET /health/live returns `{"status": "ok"}` and GET /health/ready returns `{"status": "ready", "checks": {}}` (no dependencies yet).
- Settings from environment variables with `LLM_MODE=mock` and `ENABLE_LIVE_LLM=false` by default; `hosted_free`/`live_paid` refuse to start without `ENABLE_LIVE_LLM=true`. Provider keys in the environment never switch the mode.
- JSON logs for the app's own events (uvicorn's access log is still plain text).
- A keyless, offline test suite: tests cannot open non-loopback connections or DNS lookups.
- A provider-independent model layer (feat-003, M1.1), used from Python; nothing in the HTTP API calls it yet:
  - `agentops_core.llm`: typed `ModelRequest`/`ModelResponse`, the `LLMProvider` port, a capability registry that rejects unknown models, and `LLMGateway`, which refuses a request needing tool calling, structured output or streaming the model lacks (`MODEL_CAPABILITY_UNSUPPORTED`) before any provider call, and validates structured output against its JSON Schema.
  - `agentops_llm.mock.MockLLMProvider`: deterministic replies scripted per run id, loadable from JSON files, zero cost.
  - `agentops_llm.litellm_provider.LiteLLMProvider`: LiteLLM SDK adapter that normalizes text, tool calls, usage and errors (`RATE_LIMITED`, `AUTH_FAILED`, `TIMEOUT`, `CAPABILITY_UNSUPPORTED`, `PROVIDER_UNAVAILABLE`, `BUDGET_EXCEEDED`, `INVALID_REQUEST`, `INVALID_RESPONSE`). Its capability registry holds no live models yet, so no live call is possible without registering one.
  - `agentops_llm.selection.select_provider`: mock by default, replay refuses every model call, and hosted or paid modes need `ENABLE_LIVE_LLM=true`.

- Synthetic data in PostgreSQL 17 + pgvector (feat-002, M0.2), from `datasets/synthetic/`: two tenants (`demo-a`, `demo-b`), four users with viewer/analyst/admin roles, 64 quarterly sales rows and six documents split into 13 citable chunks (`<document-id>#<n>`).
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

There is no HTTP endpoint for runs or approvals, no command-line entry for pausing and resuming runs, and no UI yet; see the roadmap.

## Quick Start

Prerequisites: Python 3.13, [uv](https://docs.astral.sh/uv/), Docker, Node.js ≥ 18 (development harness) and Git.

```bash
uv sync                                                    # install dependencies into .venv
docker compose up -d --wait postgres                       # PostgreSQL + pgvector on 127.0.0.1:55432
export DATABASE_URL=postgresql://agentops:change-me@127.0.0.1:55432/agentops
uv run python -m agentops_data migrate                     # create the schema
uv run python -m agentops_data seed                        # load datasets/synthetic
uv run python -m agentops_retrieval index                  # embed chunks (after every seed)
uv run python -m agentops_agents setup-checkpoints         # run checkpoint tables (schema owner)
export ANALYTICS_DATABASE_URL=postgresql://agentops_analytics:change-me-analytics@127.0.0.1:55432/agentops
uv run python -m agentops_agents run --run-id run-sample-q3-declines --tenant demo-a --user user-a-analyst "Analyze quarterly sales and explain the three largest declines"
export APP_DATABASE_URL=postgresql://agentops_app:change-me-app@127.0.0.1:55432/agentops
uv run python -m agentops_tools serve --tenant demo-a --user user-a-analyst --run-id run-1   # MCP over stdio
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
