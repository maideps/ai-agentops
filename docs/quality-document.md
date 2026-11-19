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

Ratings are judgments, not measurements: coverage is not measured yet (quality gates disabled), and performance has no baseline.

## Summary

- **Overall Quality Grade:** B
- **Blockers:** none
- **Areas requiring attention:** coverage not measured; uvicorn access logs are not JSON; `./init.sh` unusable until the harness supports uv (D-004); LiteLLM's Gemini/Groq paths download a tokenizer on first live call (D-005).

## Notes

- 2026-11-19: harness adopted (D-001).
- 2026-11-19: feat-001 (M0.1) passed verify-feature at commit 2e699f1. Added `apps/api/agentops_api` (Settings with mock default and live opt-in validator, JSON log formatter, health router, `create_app` factory) and `testsuite/` (network guard, settings env isolation, 16 tests). Type safety A: mypy strict clean over app and tests. Test coverage B: every declared behavior has an acceptance test; no coverage number yet. Documentation B: README, STANDARDS and D-003/D-004 updated; no API reference beyond FastAPI's generated OpenAPI.
- 2026-11-19: feat-003 (M1.1) passed verify-feature at commit c4866e3. Added `packages/core/agentops_core/llm` (typed contracts, error codes, deny-by-default capability registry, `LLMGateway`) and `packages/llm/agentops_llm` (scripted mock, LiteLLM adapter, provider selection, LiteLLM test stub); 36 feat-003 tests, 52 in the suite. Core: coverage A (every contract path exercised by the shared suite against two adapters; mutation spot-check of the capability check and live opt-in both caught), type safety A (mypy strict, no `Any`). LLM adapters: type safety B (the LiteLLM adapter handles SDK objects as `Any`), coverage B (no live provider exercised; error mapping verified with real LiteLLM exception classes).
- 2026-11-19: feat-002 (M0.2) passed verify-feature at commit 355a7d0 (all five layers, including the integration suite against Postgres). Added `packages/data/agentops_data` (SQL migrations with checksum drift detection, deterministic seed, typed tenant-scoped reads with role-based document access, migrate/seed CLI), `docker-compose.yml`, `infra/postgres/init/`, `datasets/synthetic/`, and the database readiness check in `apps/api/agentops_api/health.py`. Data package: coverage A (31 acceptance tests; tests were run failing before the implementation; mutation spot-checks of row-level security, the read-only grant and the role filter were each caught), type safety A (mypy strict). Infra: no automated check of the init script beyond the tests that depend on it.
- 2026-11-19: feat-004 (M1.2) passed verify-feature at commit 4362028 (all five layers). Added `packages/agents/agentops_agents` (7-node LangGraph workflow, typed read tools, tool and citation policy, limits as terminal states, RunDetail, run CLI) and `packages/retrieval/agentops_retrieval` (hashing embedder, chunk indexing via migration 0002, permission-filtered search, index CLI), plus `fixtures/llm/` and the recorded replay in `fixtures/replays/`. Agents: coverage A (17 feat-004 tests run failing before implementation; every terminal path tested; mutation spot-checks of citation enforcement, the LLM budget and the retrieval access filter each caught), type safety A (mypy strict; one documented `cast` at LangGraph's untyped stream output). Retrieval: coverage B (lexical embedder only; no semantic retrieval quality measured). Performance B for both: synchronous psycopg runs in worker threads.

---

_Update this document at session close: name each feature that passed (for example `feat-002`) under Notes and rate the modules it touched. `npm run clean-check` fails until every gate-verified feature is mentioned._
