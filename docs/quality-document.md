# Quality Document

Rate each module on a scale of A (excellent) / B (good) / C (acceptable) / D (needs work) / F (failing).

## Modules

| Module | Test Coverage | Type Safety | Documentation | Arch Compliance | Performance |
|---|---|---|---|---|---|
| apps/api/agentops_api (settings, logging, health, app factory) | B | A | B | A | B |
| testsuite/conftest.py (network guard, env isolation) | B | A | B | A | A |
| packages/core/agentops_core/llm (contracts, errors, registry, gateway) | A | A | B | A | B |
| packages/llm/agentops_llm (mock, LiteLLM adapter, selection, test stub) | B | B | B | A | B |
| packages/data/agentops_data (migrations, seed, typed tenant-scoped reads, CLI) | A | A | B | A | B |
| docker-compose.yml + infra/postgres/init (Postgres 17, pgvector, roles) | B | n/a | B | A | B |
| packages/agents/agentops_agents (graph, tools, policy, run detail, CLI) | A | A | B | A | B |
| packages/retrieval/agentops_retrieval (hashing embedder, indexing, search, CLI) | B | A | B | A | B |
| packages/retrieval/agentops_retrieval.benchmark + datasets/retrieval/v1 | B | A | B | A | B |
| packages/tools/agentops_tools (read tools, gateway, approvals, registry, recovery, ticket service, MCP server, CLI) | A | A | B | A | B |
| packages/telemetry/agentops_telemetry (tracing, redaction, Langfuse export) | A | A | B | A | B |
| packages/evals/agentops_evals + datasets/evals/v1 (corpus, runner, scenarios, faults, benchmark) | A | A | B | A | B |
| apps/api/agentops_api (health, feedback, live runs with quota, auth, problem details, request spans) | A | A | B | A | B |
| apps/web (replay-first Next.js static demo, Playwright e2e) | B | A | B | A | A |
| fixtures/replays + agentops_evals.replays (recorded sanitized runs) | A | A | A | A | n/a |

Ratings are judgments, not measurements: coverage is not measured yet (quality gates disabled), and performance has no baseline.

## Summary

- **Overall Quality Grade:** B (Phase 1 complete)
- **Blockers:** none
- **Areas requiring attention:** coverage not measured; uvicorn access logs are not JSON; `./init.sh` unusable until the harness supports uv (D-004); LiteLLM's Gemini/Groq paths download a tokenizer on first live call (D-005).
- **feat-012 passing:** hosted calls and live evaluation are tested with stubs and one
  owner-run free-tier Gemini 3.5 Flash-Lite run (corpus 11/50, benchmark 5/42; mostly
  abstentions, not a quality score). LLM adapter and API:
  test coverage B, type safety B/A respectively, documentation B, architecture A, performance B.
  Evaluation: coverage B, type safety A, documentation B, architecture A, performance B.
  Ratings are judgments; no live quality or provider-billing measurement is claimed.
- **feat-014 passing:** planning receives the tenant's quarters and the sales tool defaults
  to the two most recent; corpus evals-v1.1.0 tasks name their period. Live run: 2
  abstentions (was 36), 30 of 42 workflows reach report writing, 5 complete; report calls
  mostly fail on provider 503s and network outages. Workflow and tools: test coverage B,
  type safety A, documentation B, architecture A, performance B.

## Notes

- 2026-11-19: harness adopted (D-001).
- 2026-11-24: feat-013 passed verify-feature at commit bae0993 in its independent lane,
  then passed a fresh combined-tree gate at ab39535 after integrating completed feat-012.
  Changed benchmark.py and the retrieval CLI, added datasets/retrieval/v1,
  testsuite/acceptance/feat_013 and benchmarks/retrieval/v1. Adds a synthetic retrieval
  benchmark without changing ranking. Coverage B: metric denominators, rank cutoffs,
  inaccessible judgments, CLI configuration and real tenant/role retrieval are exercised;
  no coverage percentage or held-out relevance quality is claimed. Type safety A:
  strict mypy. Documentation B: reproducible commands, provenance and limits are explicit.
  Twelve acceptance tests, 94 offline tests, 120 integration tests and nine UI e2e pass.
  Measured Recall@3=1.0 and MRR=1.0 across 12 answerable queries, with four unscored
  access queries and no forbidden hits. These synthetic vocabulary-overlap scores do
  not change the B coverage/performance judgments. Optional quality/multi-repo gates
  remain SKIP, not verified. Sprint rubric: correctness B (minor CLI/typing fixes),
  completeness A, cleanliness A, continuity B (documented init/worktree and landing
  constraints); overall B.
  Combined verification: 124 offline tests, 123 integration tests and nine UI e2e
  passed; strict mypy checks 109 source files. Existing feat-012 product code, live
  reports and gate evidence are unchanged. Landing only reconciles docs/bookkeeping,
  including one invalid rule annotation in the other session's note.
- 2026-11-19: feat-001 (M0.1) passed verify-feature at commit bd1f4e7. Added `apps/api/agentops_api` (Settings with mock default and live opt-in validator, JSON log formatter, health router, `create_app` factory) and `testsuite/` (network guard, settings env isolation, 16 tests). Type safety A: mypy strict clean over app and tests. Test coverage B: every declared behavior has an acceptance test; no coverage number yet. Documentation B: README, STANDARDS and D-003/D-004 updated; no API reference beyond FastAPI's generated OpenAPI.
- 2026-11-19: feat-003 (M1.1) passed verify-feature at commit b770f9d. Added `packages/core/agentops_core/llm` (typed contracts, error codes, deny-by-default capability registry, `LLMGateway`) and `packages/llm/agentops_llm` (scripted mock, LiteLLM adapter, provider selection, LiteLLM test stub); 36 feat-003 tests, 52 in the suite. Core: coverage A (every contract path exercised by the shared suite against two adapters; mutation spot-check of the capability check and live opt-in both caught), type safety A (mypy strict, no `Any`). LLM adapters: type safety B (the LiteLLM adapter handles SDK objects as `Any`), coverage B (no live provider exercised; error mapping verified with real LiteLLM exception classes).
- 2026-11-19: feat-002 (M0.2) passed verify-feature at commit bc63625 (all five layers, including the integration suite against Postgres). Added `packages/data/agentops_data` (SQL migrations with checksum drift detection, deterministic seed, typed tenant-scoped reads with role-based document access, migrate/seed CLI), `docker-compose.yml`, `infra/postgres/init/`, `datasets/synthetic/`, and the database readiness check in `apps/api/agentops_api/health.py`. Data package: coverage A (31 acceptance tests; tests were run failing before the implementation; mutation spot-checks of row-level security, the read-only grant and the role filter were each caught), type safety A (mypy strict). Infra: no automated check of the init script beyond the tests that depend on it.
- 2026-11-19: feat-004 (M1.2) passed verify-feature at commit 3918fa8 (all five layers). Added `packages/agents/agentops_agents` (7-node LangGraph workflow, typed read tools, tool and citation policy, limits as terminal states, RunDetail, run CLI) and `packages/retrieval/agentops_retrieval` (hashing embedder, chunk indexing via migration 0002, permission-filtered search, index CLI), plus `fixtures/llm/` and the recorded replay in `fixtures/replays/`. Agents: coverage A (17 feat-004 tests run failing before implementation; every terminal path tested; mutation spot-checks of citation enforcement, the LLM budget and the retrieval access filter each caught), type safety A (mypy strict; one documented `cast` at LangGraph's untyped stream output). Retrieval: coverage B (lexical embedder only; no semantic retrieval quality measured). Performance B for both: synchronous psycopg runs in worker threads.
- 2026-11-19: feat-005 (M2.1) passed verify-feature at commit 92c0ea6 (all five layers). Added `packages/tools/agentops_tools` (read tools moved from the workflow, `ToolGateway` with permission checks, approval binding and the policy log, MCP server and stdio entry point), migration 0003 and the `agentops_app` login. Tools: coverage A (31 feat-005 tests run failing before implementation; mutation spot-checks of the hash comparison, write-path expiry, write-path principal and permission checks each caught, after correcting two mis-targeted mutants), type safety A (mypy strict). Performance B: one database connection per gateway call.
- 2026-11-19: feat-006 (M2.2) passed verify-feature at commit 404b264 (all five layers). Added the `tool_executions` registry (migration 0004), `agentops_tools.tickets` (external-style, idempotent sandbox ticket service), `ToolGateway.recover_executions`, Postgres checkpoints (`agentops_agents.checkpoints`), the approval pause and `resume_task` in `agentops_agents.workflow`, and `agentops_core.aio`. Tools and agents: coverage A (11 feat-006 tests run failing before implementation, including 8-way concurrent retries and injected crash/ambiguous faults; mutation spot-checks of the reference lookup, the recovery lease and the approval interrupt each caught), type safety A (mypy strict). Documentation B: D-010 states the at-most-once scope; the checkpoint privacy limit is recorded but not fixed.
- 2026-11-19: feat-007 (M3.1) passed verify-feature at commit 5242686 (all five layers). Added `packages/telemetry/agentops_telemetry`, `packages/evals/agentops_evals`, `datasets/evals/v1` (50 cases, builder `build_v1.py`), the feedback endpoint and problem-details middleware in `apps/api/agentops_api`, migration 0005 and `agentops_data.feedback`; the workflow now reads through the gateway. Coverage A: tests run failing before implementation (the viewer case exposed a real access gap); eleven mutated eval expectations each failed with a precise reason; mutation spot-checks of the redaction wrapper, role permission, bearer comparison and principal decision each caught. Performance B: the 50-case corpus takes about 15 s locally, one database connection per gateway call. Documentation B: the corpus scores enforcement with scripted model turns, not model quality (D-011).
- 2026-11-19: feat-008 (M4.1) passed verify-feature at commit faacefa (code at 3adeb9f, results at faacefa). Added the specialist orchestration (Research and Data Analyst subgraphs, `aggregate_evidence`) to `agentops_agents.workflow`, `agentops_evals.benchmark` and `benchmarks/orchestration/v1/`. Coverage A: tests run failing first; mutation spot-checks of the decision rule (ties adopt), role tool restriction and the specialists' abstention check each caught; benchmark measured fields identical across two runs. Documentation A: D-012 and REPORT.md state sample size, mode, limits and the single tool-call difference. Arch compliance B: feat-008's declared layers do not start Postgres although its tests need it (declaration from session 001).
- 2026-11-19: feat-009 (M5.1) passed verify-feature at commit a8b8caf (all five layers; six screenshots kept as gate evidence and reviewed). Added `apps/web` (static export, catalog and replay pages, Playwright tests that fail on any non-local request), `fixtures/replays` (five recordings) and the recorder, `POST /v1/runs` with demo-token auth and a daily cap (migration 0006, `agentops_data.quota`), the shared `agentops_api.auth`, and reviewer docs (threat model, deployment checklist, operations runbook, known limitations). Web coverage B: e2e covers every page and the key interactions; there are no component unit tests. Performance A: the demo is static files. Arch compliance B: feat-009's Layer 3 also assumes PostgreSQL is running (its live-run tests).
- 2026-11-19: feat-010 (tenant-isolated checkpoints) passed verify-feature at commit 8f7ffc3 (all five layers). Changed `agentops_agents.checkpoints` (row-level security on the checkpoint tables, tenant-scoped saver connections) and `agentops_agents.workflow` (tenant-carrying thread ids, `resume_task(tenant_id=...)`). Coverage A: 5 tests run failing first (a forged cross-tenant checkpoint write was accepted before the change); mutation spot-checks of the RLS policies and of thread-id tenant validation each caught. Its declared layers start PostgreSQL themselves. Also this session: CI actions moved to Node 24 versions pinned by commit SHA (da138c1).
- 2026-11-19: feat-011 (HTTP approvals and resume) passed verify-feature at commit 9f7ae40 (all five layers). Changed `apps/api/agentops_api/runs.py` (propose_followup, GET run, approval decision plus resume, tenant-scoped checkpointer for every API run) and added `agentops_agents.workflow.load_run`. Coverage A: 10 tests run failing first; the 409 mapping mutant was caught; a mutant hard-wiring the checkpointer's tenant survived because the authenticated thread id alone keeps tenants apart (row-level security is the second layer, tested in feat-010), recorded in D-015.

---

_Update this document at session close: name each feature that passed (for example `feat-002`) under Notes and rate the modules it touched. `npm run clean-check` fails until every gate-verified feature is mentioned._
