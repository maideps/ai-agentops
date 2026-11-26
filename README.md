# AI AgentOps

A security-first agentic AI platform you can run on a laptop without any API key. An agent analyzes synthetic sales data, retrieves only the documents the user may read, writes a report in which every finding cites its evidence, and proposes a follow-up ticket that is written only after a person approves it, exactly once. It runs on a scripted mock model by default; a real model (Gemini Flash-Lite) is opt-in, budgeted and measured.

The point of the project is the platform around the model: the model proposes, the server decides. Tenant isolation, role permissions, approvals, idempotent writes, limits, redacted traces and evaluation are enforced by code and tests, not by the prompt.

## Table of Contents

- [What It Does](#what-it-does)
- [Architecture](#architecture)
- [Measured Results](#measured-results)
- [Quick Start](#quick-start)
- [Usage](#usage)
- [Reproduce the Tests](#reproduce-the-tests)
- [Development](#development)
- [Roadmap](#roadmap)
- [Documentation](#documentation)
- [License](#license)

## What It Does

**A bounded agent workflow.** One LangGraph graph validates the user, plans tool calls, authorizes them, runs them, writes a cited report, filters unsupported citations and, when asked, pauses for approval of a follow-up ticket. Each run is limited to 6 model calls, 8 tool calls, 16 graph steps and 90 seconds, and always ends with an explicit status: completed, abstained, rejected, budget exhausted, timed out or failed. An experimental orchestration splits planning into Research and Data Analyst subgraphs; the single workflow stays the default.

**The model only proposes.** Every tool call goes through a server-side gateway: an allowlist, the user's role permissions (a viewer cannot read sales), strict arguments that never carry a tenant or user, and an append-only policy log. A finding that cites evidence the model never saw is dropped; with nothing supported left, the run abstains. A prompt-injection payload in a retrieved document is treated as data, and the actions it asks for are refused.

**Partial answers say so.** When the gateway denies a whole source to the user's role, the run records it as an evidence gap, and the report step is told not to claim what needs it. Documents a role cannot read are never listed, so they stay indistinguishable from missing ones.

**Writes happen once, after approval.** The only write is a sandbox ticket. It needs an approval bound to the user, the run, the policy version and the hash of the exact arguments, consumed in the same transaction. An execution registry and reconciliation keep it to one ticket under concurrent retries or a crash mid-write. Paused runs are checkpointed in PostgreSQL per tenant and resume in any process.

**Tenants are isolated in the database.** PostgreSQL row-level security keys every tenant table, the analytics login is read-only, and checkpoints carry the tenant in their thread id.

**Real-model calls are opt-in and capped.** Gemini runs only with a live mode, `ENABLE_LIVE_LLM=true`, a key and an explicit budget. Before every attempt the adapter reserves the worst case. It can space calls apart, retries server errors, connection errors and per-minute rate limits at most twice, and fails a daily-quota error at once. Tests and the demo never call a provider.

**Everything is traced and evaluated.** OpenTelemetry spans share each run's trace id and pass a redaction layer: ids, counts and codes, never prompts, documents or keys. A versioned 50-case evaluation corpus checks normal, multi-source, missing-data, tool-misuse, injection, access, reliability and budget cases. Live runs are scored on outcomes plus safety invariants, and stop early when the provider's daily quota runs out.

**A replay-first demo.** A static Next.js site shows five recorded runs (a cited analysis, a viewer denied sales data, missing data, a prompt injection, and a ticket written after approval) with their report, evidence, evidence gaps, policy decisions, approval and trace. It sends no request to any backend or model provider.

## Architecture

```text
Presentation    apps/api (FastAPI)              apps/web (replay demo)
Application     packages/agents (workflow)      packages/tools (gateway, MCP)    packages/evals
Domain          packages/core (contracts and ports, no SDKs)
Infrastructure  packages/llm   packages/data   packages/retrieval   packages/telemetry
External        PostgreSQL 17 + pgvector        Gemini (opt-in)
```

Layers depend only on the layers below them, and architecture rules checked on every run of `npm run check` keep it that way (for example, LiteLLM may be imported only in `packages/llm`).

- [`docs/architecture-map.html`](docs/architecture-map.html): an interactive map of the components, one request step by step, where each security control applies, and the feature history. Clone the repository and open it in a browser.
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md): the layer model, enforced rules and design notes.
- [`docs/ARCHITECTURE_AND_REQUIREMENTS.md`](docs/ARCHITECTURE_AND_REQUIREMENTS.md): the full specification, including the threat model and failure matrix.

## Measured Results

All data is synthetic. Mock-mode results check the platform's enforcement with scripted model replies; they say nothing about model quality.

| Measurement | Result | Evidence |
|---|---|---|
| Evaluation corpus, mock mode (`evals-v1.3.0`) | 50/50 | `uv run python -m agentops_evals run` |
| Single workflow vs specialists, mock mode | 42/42 each; specialists use about one more model call per run (2.74 vs 1.81) | [report](benchmarks/orchestration/v1/REPORT.md) |
| Retrieval, synthetic v1 queries | Recall@3 1.0, MRR 1.0, no forbidden hits | [results](benchmarks/retrieval/v1/results.json) |
| Retrieval, harder stress queries | Recall@3 0.76, MRR 0.74; BM25 reaches 0.83 and 0.80 with individual regressions and is not adopted | [stress](benchmarks/retrieval/stress-v2/REPORT.md), [BM25](benchmarks/retrieval/bm25-v1/REPORT.md) |

Five owner-approved runs with Gemini 3.5 Flash-Lite on the free tier (2026-11-24 to 2026-11-26). Each fixed the main failure of the one before:

| Run | Live result | What limited it | Fixed by |
|---|---|---|---|
| 1 | corpus 11/50 | the model invented quarters with no data and abstained | feat-014: planning is told the available quarters |
| 2 | corpus 11/50 | abstentions fell from 36 to 2, but report calls failed on provider overload (HTTP 503) | feat-015: bounded retries |
| 3 | corpus 11/50, 22/42 workflows completed | expectations scored the mock's scripted trajectory, not the answer | feat-017: outcome-based live scoring |
| 4 | 29/41 live outcomes | all 12 failures were free-tier rate limits | feat-019: pacing and rate-limit retries |
| 5 | 37/41 live outcomes; benchmark 37/41 single, 38/41 specialists | three multi-source reports cited no policy document; a viewer's run answered from permitted documents instead of abstaining | feat-018 and feat-023, not yet measured live |

Run 5 is in `benchmarks/evals/v1.2/live-feat019/` and `benchmarks/orchestration/v1/live-feat019/`. The benchmark's rule recommends specialists by that one case; the single workflow remains the default until a repeated run confirms the difference. See [known limitations](docs/known-limitations.md) for what these numbers do not show.

## Quick Start

Prerequisites: Python 3.13, [uv](https://docs.astral.sh/uv/), Docker, Node.js 18 or later (development harness and the demo UI) and Git.

```bash
uv sync                                                    # install dependencies into .venv
docker compose up -d --wait postgres                       # PostgreSQL + pgvector on 127.0.0.1:15432
export DATABASE_URL=postgresql://agentops:change-me@127.0.0.1:15432/agentops
uv run python -m agentops_data migrate                     # create the schema
uv run python -m agentops_data seed                        # load datasets/synthetic
uv run python -m agentops_retrieval index                  # embed chunks (after every seed)
uv run python -m agentops_agents setup-checkpoints         # run checkpoint tables (schema owner)
export ANALYTICS_DATABASE_URL=postgresql://agentops_analytics:change-me-analytics@127.0.0.1:15432/agentops
export APP_DATABASE_URL=postgresql://agentops_app:change-me-app@127.0.0.1:15432/agentops
uv run python -m agentops_agents run --run-id run-sample-q3-declines --tenant demo-a --user user-a-analyst "Analyze quarterly sales and explain the three largest declines"
```

The last command prints the run detail as JSON: for `demo-a`'s analyst, the three largest 2026-Q2 to Q3 declines (Trail Running Shoes EMEA −4,000, Rain Jacket NA −3,000, Camping Stove NA −2,000), each finding citing sales records and policy passages, and every policy decision of the run.

The compose file uses throwaway local passwords (`POSTGRES_PASSWORD`, `ANALYTICS_DB_PASSWORD`, `APP_DB_PASSWORD` override them). Database roles are created only with the data volume; after changing `infra/postgres/init/`, recreate it with `docker compose down -v`. Settings come from environment variables; copy `.env.example` to `.env` and pass it with `--env-file .env` to use a file. Do not run `./init.sh`: it would install into the system Python (D-004 in `DECISIONS.md`).

For the demo UI alone, only Node is needed: `npm ci --prefix apps/web`, `npm --prefix apps/web run build`, `npm --prefix apps/web run serve`, then open http://127.0.0.1:4173/.

## Usage

**HTTP API.** Start it with `uv run uvicorn agentops_api.app:create_app --factory` (http://127.0.0.1:8000).

| Route | What it does |
|---|---|
| GET /health/live, GET /health/ready | liveness; readiness checks PostgreSQL when `DATABASE_URL` is set |
| POST /v1/runs | runs a task for the demo user (bearer `DEMO_API_TOKEN`), capped at `MAX_REQUESTS_PER_DEMO_USER` runs a day; with `"propose_followup": true` it returns `awaiting_approval` and the bound proposal |
| GET /v1/runs/{run_id} | the run's current detail, from its checkpoint |
| POST /v1/runs/{run_id}/approvals/{approval_id} | `{"decision": "approve"}` or `"reject"` resumes the run; a second decision is 409, another user 403, another tenant 404 |
| POST /v1/runs/{run_id}/feedback | stores a thumbs up or down with an optional comment |

**Command line.**

```bash
uv run python -m agentops_tools serve --tenant demo-a --user user-a-analyst --run-id run-1   # MCP server over stdio
uv run python -m agentops_tools recover --tenant demo-a           # reconcile stuck ticket writes
uv run python -m agentops_evals run --out evals-report.json       # 50-case corpus, mock mode
uv run python -m agentops_evals benchmark                         # single workflow vs specialists
uv run python -m agentops_evals record-replays                    # re-record the demo replays
uv run python -m agentops_retrieval benchmark --git-sha "$(git rev-parse HEAD)" --out retrieval-results.json
uv run python -m agentops_retrieval compare --help                # vector search vs BM25, read-only
uv run python -m agentops_data export-feedback --tenant demo-a
```

**Live model (opt-in).** The evaluation commands stay on the mock unless given `--live` and `--budget-usd` (a live corpus run also needs `--out`), with `LLM_MODE=hosted_free`, `ENABLE_LIVE_LLM=true` and `GEMINI_API_KEY` set. The API additionally needs `LLM_MODEL=gemini/gemini-3.5-flash-lite` and an explicit `LLM_BUDGET_USD`. `--min-call-interval` spaces calls for free-tier limits and `--stop-after-rate-limited` sets the early-stop streak. The budget cap covers the whole command and reservations are deliberately conservative. See the [manual live procedure](docs/runbooks/operations.md#manual-hosted-evaluation).

## Reproduce the Tests

```bash
docker compose up -d --wait postgres
uv sync
npm ci --prefix apps/web && npx --prefix apps/web playwright install chromium
npm run check                                              # lint, types, offline tests, architecture rules, replay UI e2e
uv run pytest testsuite -q -m integration                  # tenant isolation, approvals, crash recovery, checkpoints, replays
npm --prefix apps/web run e2e                              # replay UI only: screenshots in apps/web/test-results/shots
```

The default test suite is keyless and offline: tests cannot open non-loopback connections or DNS lookups.

## Development

The repository is built feature by feature with an agent harness: each feature is declared in [`feature_list.json`](feature_list.json), implemented on a branch and accepted only when its verification gate passes. Gate evidence is in `.harness/state/`, sessions in `progress/` and decisions in [`DECISIONS.md`](DECISIONS.md). See [`AGENTS.md`](AGENTS.md) and the [command reference](docs/HARNESS.md).

```bash
npm run activate -- feat-001
npm run verify-feature -- feat-001
```

## Roadmap

Phase 1 (M0 to M5) is the release scope of the specification; Phase 2 hardens it with evidence from real-model runs. Progress is summarized in [`PROGRESS.md`](PROGRESS.md).

| Feature | Milestone | Slice |
|---|---|---|
| feat-001 | M0.1 | Keyless FastAPI skeleton, health endpoints, settings, logging, Ruff, mypy, pytest, CI |
| feat-002 | M0.2 | PostgreSQL + pgvector, migrations, two synthetic tenants, read-only role |
| feat-003 | M1.1 | `LLMProvider` port, mock provider, LiteLLM adapter, capability registry |
| feat-004 | M1.2 | First LangGraph workflow: SQL + retrieval → cited report, abstention |
| feat-005 | M2.1 | First-party MCP server, policy gateway, approval binding, sandbox ticket |
| feat-006 | M2.2 | Postgres checkpointing, execution registry, crash recovery, reconciliation |
| feat-007 | M3.1 | Redacted telemetry, feedback API, 50-case evaluation corpus |
| feat-008 | M4.1 | Three-specialist comparison against the single-workflow baseline |
| feat-009 | M5.1 | Replay-first Next.js demo and portfolio evidence |
| feat-010 | Phase 2 | Tenant-isolated run checkpoints |
| feat-011 | Phase 2 | Approvals over HTTP and run resume |
| feat-012 | Phase 2 | Budgeted Gemini calls and opt-in live evaluation |
| feat-013 | Phase 2 | Read-only retrieval relevance baseline |
| feat-014 | Phase 2 | Planning is told the tenant's sales quarters |
| feat-015 | Phase 2 | Bounded retries for transient provider failures; 1,024-token output |
| feat-016 | Phase 2 | Retrieval stress queries and comparison |
| feat-017 | Phase 2 | Live evaluation scores outcomes, not mock trajectories |
| feat-018 | Phase 2 | Policy citation guidance in the report prompt |
| feat-019 | Phase 2 | Paced live calls and rate-limit retries |
| feat-020 | Phase 2 | Offline BM25 comparison; production retrieval unchanged |
| feat-021 | Phase 2 | Live evaluation stops when the daily quota runs out |
| feat-022 | Phase 2 | Repository ready to be public |
| feat-023 | Phase 2 | Runs record the sources the user's role kept from them |
| feat-024 | Phase 2 | Demo replays current and repeatable; run ids single-use |

Next: a live run that measures feat-018 and feat-023 together.

## Documentation

- [Product overview](docs/PRODUCT.md)
- [Requirements and architecture (authoritative)](docs/ARCHITECTURE_AND_REQUIREMENTS.md)
- [Architecture summary and enforced rules](docs/ARCHITECTURE.md) and the [interactive map](docs/architecture-map.html)
- [Threat model](docs/threat-model.md)
- [Known limitations](docs/known-limitations.md)
- [Operations runbook](docs/runbooks/operations.md) and [deployment checklist](docs/runbooks/deployment-checklist.md)
- [Retrieval baseline](docs/retrieval-baseline.md)
- [Project standards](docs/STANDARDS.md) and [engineering handoff](docs/CLAUDE_CODE_HANDOFF.md)
- [Decisions](DECISIONS.md)
- [Harness usage guide](docs/USAGE.md) and [command reference](docs/HARNESS.md)
- [Security policy](SECURITY.md) and [publishing checks](docs/publishing.md)

## License

MIT, see [`LICENSE`](LICENSE).
