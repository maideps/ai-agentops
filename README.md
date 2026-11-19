# AgentOps AI

A provider-agnostic, security-first agentic AI platform (portfolio project). It analyzes synthetic sales data, retrieves permission-filtered evidence, writes cited reports and proposes follow-up actions that run only after human approval, exactly once. It runs mock-first, with no paid model calls by default.

## Table of Contents

- [Status](#status)
- [Quick Start](#quick-start)
- [Usage](#usage)
- [Roadmap](#roadmap)
- [Documentation](#documentation)
- [License](#license)

## Status

Early stage (feat-001 M0.1, feat-002 M0.2 and feat-003 M1.1 done). What works today:

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

There is no agent workflow or UI yet; see the roadmap.

## Quick Start

Prerequisites: Python 3.13, [uv](https://docs.astral.sh/uv/), Docker, Node.js ≥ 18 (development harness) and Git.

```bash
uv sync                                                    # install dependencies into .venv
docker compose up -d --wait postgres                       # PostgreSQL + pgvector on 127.0.0.1:55432
export DATABASE_URL=postgresql://agentops:change-me@127.0.0.1:55432/agentops
uv run python -m agentops_data migrate                     # create the schema
uv run python -m agentops_data seed                        # load datasets/synthetic
uv run uvicorn agentops_api.app:create_app --factory       # serve the API on http://127.0.0.1:8000
curl http://127.0.0.1:8000/health/ready
npm run check                                              # lint, types, offline tests, harness checks
uv run pytest testsuite -q -m integration                  # tests against the local database
```

The compose file uses throwaway local passwords (`POSTGRES_PASSWORD`, `ANALYTICS_DB_PASSWORD` override them). Database roles are created only when the data volume is first created; after changing `infra/postgres/init/`, recreate it with `docker compose down -v`.

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
