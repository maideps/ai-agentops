# Architectural Decisions Log

This file records significant architectural decisions, their context, alternatives considered, and consequences. It serves as durable cross-session memory for why the codebase is structured the way it is.

## Decision Template

```
### D-XXX: [Decision Title]

**Date:** YYYY-MM-DD
**Status:** proposed | accepted | deprecated | superseded by D-YYY
**Context:** [What problem are we solving? What constraints exist?]
**Decision:** [What did we decide to do?]
**Alternatives considered:**
- Alternative 1: [description] — Rejected because [reason]
**Consequences:**
- Positive: [benefits gained]
- Negative: [tradeoffs accepted]
```

## Recorded Decisions

<!-- Add decision records here, newest last. Expand long records into docs/decisions/ and link back from here. -->

### D-001: Develop under the AI Harness Framework

**Date:** 2026-11-19
**Status:** accepted
**Context:** The handoff requires one vertical slice at a time, tested evidence before "done", ADRs and per-feature reports, across many agent sessions. Written rules alone do not stop an agent from skipping checks or starting a second slice.
**Decision:** Adopt ai-harness-framework v0.5.0 (vendored by `create-harness`, upstream commit b41fefd) as the development harness. Milestones M0.1–M5.1 become features feat-001–feat-009 in `feature_list.json`; a feature passes only through `npm run verify-feature`. Project rules formerly in `docs/CLAUDE.md` moved to `docs/STANDARDS.md` and `docs/PRODUCT.md`, because the root `AGENTS.md`/`CLAUDE.md` are harness CORE files replaced on upgrade.
**Alternatives considered:**
- Rules in a hand-written `CLAUDE.md` only — Rejected: nothing enforces WIP=1 or evidence.
- Install from npm instead of vendoring — Deferred: vendoring needs no network at check time; `harness-upgrade` can refresh CORE later.
**Consequences:**
- Positive: enforced WIP=1 and dependency order, commit-bound evidence, session continuity, `forbid` rules for product invariants.
- Negative: Node ≥ 18 is required next to Python; each feature needs a session note, a README update and a quality-document entry.
- Reversal: delete the harness CORE files and `.harness/`; product code does not depend on them.

### D-002: Product tests live in `testsuite/`, not `tests/`

**Date:** 2026-11-19
**Status:** accepted
**Context:** The spec's suggested layout puts product tests in `tests/`, but the harness classifies `tests/` as CORE (its own self-tests) and `harness-upgrade` overwrites it.
**Decision:** Product tests go in `testsuite/{acceptance,unit,contracts,integration,security,reliability,evals,live}/`, declared in the manifest's `productRoots`. `testsuite/acceptance/feat_NNN/` holds the declared-behavior tests of one feature. Spec §11.3 and handoff §3 were updated to match.
**Alternatives considered:**
- Mix product tests into `tests/` — Rejected: misclassified as harness CORE; upgrades could overwrite them.
- Tests next to each package only — Rejected: security and reliability suites cut across packages.
**Consequences:**
- Positive: harness upgrades never touch product tests; arch-005 classifies them correctly.
- Negative: a non-standard directory name; pytest must be pointed at `testsuite/` (`testpaths` in `pyproject.toml`).

### D-003: Python checks are declared per feature with `uv run`

**Date:** 2026-11-19
**Status:** accepted
**Context:** The harness's Python stack detection runs global `ruff`/`mypy`/`pytest` and hard-codes `mypy src/`; this project uses a uv virtualenv and `apps/` + `packages/`. The harness's `npm run lint`/`test` scripts check harness state only.
**Decision:** Each feature in `feature_list.json` declares its own layers: (1) harness checks `node scripts/framework-check.mjs lint && npm run check-arch && node scripts/framework-check.mjs typecheck` (called directly, because the npm `lint`/`typecheck` scripts also run the Python checks of layer 2); (2) Python static checks `uv run ruff check . && uv run ruff format --check . && uv run mypy`; (3) the feature's acceptance tests; (4) the default regression suite; plus an integration layer for features that need Postgres. feat-001 also chains the uv commands into the `package.json` `lint`/`typecheck`/`test` scripts so `npm run check` and CI run them.
**Alternatives considered:**
- Rely on stack detection — Rejected: SKIPs inside a uv venv and checks a non-existent `src/`.
**Consequences:**
- Positive: the gate runs exactly the project's commands; nothing depends on an activated venv.
- Negative: layer commands are repeated across features; changing one means updating several declarations (and re-verifying, since `checksHash` changes).

### D-004: Do not run `./init.sh` or `npm run setup` until the harness supports uv

**Date:** 2026-11-19
**Status:** accepted (temporary)
**Context:** Once `pyproject.toml` exists, the harness detects a Python stack and its install step is `pip install -e ".[dev]"`; `./init.sh` and `npm run setup` run it with whatever Python is on PATH, outside the uv virtualenv, and init.sh's verification chain runs the global `python -m pytest`. Those files are harness CORE and must not be edited here.
**Decision:** Until the framework learns uv (detect `uv.lock`, install with `uv sync --locked`, run layers with `uv run`), sessions start with `uv sync` and `node scripts/framework-check.mjs brief` instead of `./init.sh`, and run `node scripts/framework-check.mjs selftest` when the harness self-tests are needed. CI installs with `astral-sh/setup-uv` and `uv sync --locked` instead of `npm run setup`.
**Alternatives considered:**
- Edit `init.sh`/`stack-detect.mjs` locally — Rejected: CORE files are overwritten by `harness-upgrade`.
- Move `pyproject.toml` out of the root so the harness sees a node stack — Rejected: fights uv's project discovery and every tool's config lookup.
**Consequences:**
- Positive: nothing installs into the system Python.
- Negative: the harness's documented startup (`./init.sh`) is skipped; `AGENTS.md` still tells agents to run it, so `docs/STANDARDS.md` overrides it explicitly.
- Reversal: once an upstream harness release handles uv (maideps/ai-harness-framework#63 and #64), run `harness-upgrade`, confirm `./init.sh` uses `uv sync`, and mark this decision superseded.

### D-005: LLM port shape, gateway placement and error codes

**Date:** 2026-11-19
**Status:** accepted
**Context:** Spec 5.1 proposes `ModelRequest` with untyped messages and a `response_schema_name`, and two names for the capability error (`MODEL_CAPABILITY_UNSUPPORTED` in FR-010, `CAPABILITY_UNSUPPORTED` in 5.2). Tool calling and JSON-schema output need the tool definitions and the schema itself, not only a name.
**Decision:**
- Typed `Message`, `ToolDefinition`, `ResponseSchema` (name + JSON Schema) in `packages/core`; the port is `async generate(request, model)` plus `capabilities(model)`.
- `LLMGateway` (core) runs the capability check before every provider call and validates structured output with JSON Schema (Draft 2020-12) for every provider, so adapters cannot drift.
- `MODEL_CAPABILITY_UNSUPPORTED` = our registry refused before execution; `CAPABILITY_UNSUPPORTED` = the provider refused a parameter. Added `INVALID_REQUEST` (provider 400/404) and `INVALID_RESPONSE` (unparseable tool arguments or schema-violating output). Error messages carry only the exception type, never provider text, and are raised `from None` so provider messages are not chained into logs.
- The capability registry denies unknown models. It holds only the mock model today; a live model is registered only after a live smoke test confirms its capabilities.
- The mock is scripted per `run_id` (turns returned in order), loadable from JSON files.
**Alternatives considered:**
- Keep `response_schema_name` with a server-side schema registry — Deferred: no schemas exist yet; the name is kept inside `ResponseSchema`.
- Validate structured output inside each adapter — Rejected: duplicated logic, and the mock could pass what LiteLLM fails.
**Consequences:**
- Positive: one contract suite runs unchanged against the mock and the LiteLLM adapter; capability failures never reach a provider.
- Negative: spec 5.1 needed an "as implemented" note; adding a live model needs a registry entry.
- Known limitation: LiteLLM 1.108.0's Gemini and Groq paths load the `cl100k_base` tokenizer, which its wheel does not bundle, so the first live call downloads it from openaipublic.blob.core.windows.net (tiktoken checks its hash). The OpenAI path goes straight to the provider. Revisit before the first live smoke test (vendor the file via `CUSTOM_TIKTOKEN_CACHE_DIR` or upgrade LiteLLM).

### D-006: 14-day release cooldown for Python dependencies

**Date:** 2026-11-19
**Status:** accepted
**Context:** LiteLLM was compromised on PyPI in March 2026 (malicious 1.82.7/1.82.8 releases). The newest LiteLLM when feat-003 started was uploaded the same day.
**Decision:** `[tool.uv] exclude-newer` in `pyproject.toml` resolves only releases published before a fixed date about 14 days in the past (currently 2026-11-05). Moving it is a deliberate commit that re-locks and reviews what changed. After any dependency change, check that no unexpected `.pth` file appeared in `.venv`.
**Alternatives considered:**
- Pin only LiteLLM — Rejected: the same risk applies to every transitive dependency.
**Consequences:**
- Positive: a freshly published malicious release cannot enter the lock before the community has had time to catch it.
- Negative: urgent security fixes need a deliberate date bump; resolved versions lag upstream (for example fastapi 0.162.0, litellm 1.108.0).

### D-007: Tenant isolation with row-level security, a read-only login and typed reads

**Date:** 2026-11-19
**Status:** accepted
**Context:** FR-003/FR-004 need tenant-scoped, read-only analytics over synthetic data, enforced by the database and not only by application code, with stable ids for citations.
**Decision:**
- **Isolation in two layers.** Tenant tables have row-level security policies on `current_setting('app.tenant_id', true)`; an unset tenant matches no rows. The typed functions in `agentops_data.access` set it per transaction with `set_config(..., true)` and also filter by tenant in SQL. There is no function that accepts SQL text.
- **Roles.** `agentops` owns the schema and runs migrations and the seed. `agentops_readonly` (NOLOGIN) holds `SELECT` grants only; `agentops_analytics` (LOGIN, NOBYPASSRLS) inherits it. Login roles and passwords come from the compose init script (`infra/postgres/init/`), so migrations never contain credentials.
- **Document ACL.** `role_document_access` maps roles to access labels (viewer: public; analyst: public + internal; admin: all). A missing and a forbidden document raise the same `DocumentNotAccessibleError`.
- **Migrations** are plain SQL files in `agentops_data/migrations/`, applied in order, recorded with a SHA-256 checksum; an edited applied file fails with `MigrationDriftError`. No ORM, no Alembic.
- **Local layout.** Postgres 17 + pgvector 0.8.0 pinned by digest, on `127.0.0.1:55432` (5432 was taken by a locally installed PostgreSQL). Integration tests use a separate `agentops_test` database.
- **pgvector** is installed now; the embedding column and its dimension are chosen with retrieval in feat-004.
**Alternatives considered:**
- `SET ROLE` on the owner connection — Rejected: the session could `RESET ROLE` back to the owner.
- Application-side tenant filters only — Rejected: one missed `WHERE` leaks across tenants.
- Alembic — Deferred: no ORM models; SQL files are easier to review.
**Consequences:**
- Positive: a query without a tenant scope returns nothing; writes through the analytics login fail on privileges, whatever SQL is sent.
- Negative / limits: the analytics login can still `set_config('app.tenant_id', ...)` itself if it can run arbitrary SQL, so RLS limits a scoped connection, not a hostile one; the typed functions and the tool gateway (feat-005) remain required. The init script runs only on a fresh volume: after changing it, recreate with `docker compose down -v`. The least-privilege application role for writes arrives with the first write path (feat-005/006).

### D-008: First workflow: one bounded LangGraph graph, offline hashing embeddings

**Date:** 2026-11-19
**Status:** accepted
**Context:** feat-004 (M1.2) needs one task to go from authorized sales data and document evidence to a cited report, reproducibly in mock mode, with no network, GPU or paid API, and with visible policy decisions and limits.
**Decision:**
- **Graph:** one LangGraph `StateGraph` with 7 nodes: `validate_request → plan → authorize_tools → execute_tools → synthesize_report → output_policy → finalize`. Any node may set a terminal status (`rejected`, `abstained`, `budget_exhausted`, `timed_out`, `failed`) and route to `finalize`. No specialist agents yet (M4.1 compares them against this baseline). No checkpointer yet (feat-006).
- **Limits (FR-011):** LLM calls and tool calls are counted in state and checked before each call; the deadline is checked before every node; LangGraph's `recursion_limit` is the step limit. Each exhaustion ends the run with its own error code (`MAX_LLM_CALLS`, `MAX_TOOL_CALLS`, `MAX_RUN_SECONDS`, `MAX_GRAPH_STEPS`).
- **Policy, not the model, decides:** tool calls pass an allowlist and strict argument schemas (`extra="forbid"`, so a smuggled `tenant_id` is denied); tenant and user always come from the run's principal. After synthesis, findings citing anything not in the model's context are dropped (`UNSUPPORTED_CITATION`). Every decision is recorded with `POLICY_VERSION`.
- **Abstention (FR-012):** no sales rows for the requested quarters → `NO_SALES_DATA` without a synthesis call; no evidence → `NO_EVIDENCE`; no finding left after the citation check → `NO_SUPPORTED_FINDINGS`.
- **Context budget:** verified sales evidence first, then documents by relevance, up to `max_context_tokens` (word-count estimate); dropped ids are recorded.
- **Embeddings:** `HashingEmbedder` (feature hashing of word tokens, 256 dimensions, blake2b) behind an `Embedder` protocol, stored in `document_chunks.embedding` with its `embedding_model`. Deterministic and offline, but lexical, not semantic. Retrieval filters by tenant and role inside the ranking query.
- **Run detail:** `RunDetail` is the sanitized result (report, analytics, evidence, context window, policy decisions, errors, call and token counts, trace id). The trace id is a correlation id for now; OpenTelemetry spans arrive in feat-007. The sample run is recorded in `fixtures/replays/` and the test fails if a run stops reproducing it.
- **Mock model:** scripted per run id from `fixtures/llm/`; a run id without a script fails with `PROVIDER_UNAVAILABLE`.
- **LangSmith** (installed with LangGraph) traces only when `LANGSMITH_TRACING` is set; tests clear it and the network guard would block it.
**Alternatives considered:**
- A local sentence-embedding model (ONNX) — Deferred: a model download, slower CI, and nothing to gain on a 13-chunk synthetic corpus.
- Provider embeddings through LiteLLM — Rejected for mock mode: needs network and keys.
- Three specialist agents now — Rejected by the handoff: measure the single workflow first.
**Consequences:**
- Positive: the whole slice runs offline and deterministically; every policy and limit path has a test.
- Negative: hashing retrieval only matches shared words; the mock script is tied to run ids; database calls are synchronous psycopg run in worker threads; there is no HTTP endpoint for runs yet (`python -m agentops_agents run` is the entry point).

### D-009: Tool gateway, approval binding and a principal-bound MCP server

**Date:** 2026-11-19
**Status:** accepted
**Context:** FR-005/FR-006 need a first-party MCP server with read tools and one sandbox write, authorization enforced server-side (not by MCP or the model), and writes that require an approval bound to principal, action-payload hash, policy version, expiry and run.
**Decision:**
- **`ToolGateway` (`packages/tools`) is the only decision point.** Order of checks: tool allowlisted → well-formed run id → principal exists in the tenant → role has the tool's permission (`role_permissions`: `sales:read`, `docs:read`, `issues:read`, `tickets:write`) → arguments valid against a strict model (`extra="forbid"`). Every outcome is written to the append-only `policy_events` table, denials in their own committed transaction.
- **Approval binding.** `request_approval` stores the SHA-256 of canonical JSON over tool, tenant, principal, run, policy version and arguments, with an expiry (15 minutes by default, database clock). Only the requesting principal can approve or reject it, for the same run. `invoke` with an approval locks the row (`SELECT … FOR UPDATE`), checks principal, run, tool, status, expiry, policy version and hash, then marks it consumed and inserts the ticket in the same transaction. One approval writes at most one ticket; a second use fails with `APPROVAL_ALREADY_USED`. The ticket id is derived from the approval id (`SBX-…`).
- **MCP server (MCP Python SDK 2.x `MCPServer`)** is built per principal and run by the trusted backend (`build_server(gateway, ctx)`, or `python -m agentops_tools serve` over stdio). Tool parameters never include identity; every call is forwarded to the gateway, and denials become MCP tool errors carrying the reason code.
- **Least privilege.** New login `agentops_app` (group `agentops_app_rw`): `SELECT`/`INSERT` on approvals, tickets and the policy log, `UPDATE` only of approval status columns, no `DELETE` anywhere. Row-level security `FOR ALL` policies make the same tenant check the `WITH CHECK` for writes. arch-105 forbids writes to approvals or tickets outside the gateway.
- **Prompt injection.** A synthetic `demo-b` document carries an injection payload. Tests show retrieval returns it as data, and that each step a model obeying it would take is refused (smuggled tenant id, write without approval). This tests the enforcement, not the model's resistance.
- **Read tools moved** from `agentops_agents` to `agentops_tools.read_tools`, so the workflow and the gateway share one implementation and `agentops_tools` never imports the workflow. `POLICY_VERSION` moved to `agentops_core.policy`.
**Alternatives considered:**
- Principal as a tool argument — Rejected: the model could set it.
- Approval checks inside the MCP server — Rejected: MCP is the transport; the gateway must hold even if MCP is bypassed.
- An approval-free "low-risk write" path — Rejected for Phase 1: every external write needs approval.
**Consequences:**
- Positive: forged, pending, rejected, expired, mutated, replayed, other-principal, other-run, other-tenant and stale-policy approvals all fail closed with no write, and each attempt is logged.
- Negative / limits: the feat-004 workflow still calls its read tools directly (typed and tenant-scoped, but not logged in `policy_events`) and does not yet propose tickets; routing it through the gateway with an approval interrupt comes with checkpointing in feat-006. Atomicity here relies on the ticket store being the same database; an external ticket system needs the idempotency registry and reconciliation of feat-006. There is no HTTP approval endpoint yet. Existing development databases need the new roles created once (the init script only runs on a fresh volume).

### D-010: Execution registry, external-style ticket service, Postgres checkpoints and the approval pause

**Date:** 2026-11-19
**Status:** accepted
**Context:** FR-007/FR-008 and NFR-003 need writes that survive retries, concurrent duplicates and crashes, and runs that pause for human approval and resume after a process restart. In feat-005 the ticket insert shared one transaction with the approval, so a "crash after the external commit" could not happen and could not be tested.
**Decision:**
- **The sandbox ticket service behaves like an external system** (`agentops_tools.tickets`): it commits on its own, is idempotent on the caller's external reference (a repeat with the same content returns the same ticket; different content under the same reference is rejected), and can be queried by reference.
- **Registry (`tool_executions`, migration 0004).** `UNIQUE (tenant_id, tool_name, idempotency_key)`; the key is derived server-side from the approval (`approval:<id>`), the external reference from the approval id (`SBX-…`). The gateway (1) verifies the approval and, in the same transaction, reserves the execution and consumes the approval; (2) claims it (`reserved|uncertain → executing`, attempt + 1); (3) calls the ticket service; (4) records `succeeded`, `failed` (definite rejection) or `uncertain` (outcome unknown). Concurrent retries serialize on the approval row lock: one reserves, the rest get `APPROVAL_ALREADY_USED`.
- **Recovery (`ToolGateway.recover_executions`, `python -m agentops_tools recover`).** `uncertain` rows, and `executing` rows idle longer than a lease (default 5 minutes), are looked up by external reference first: found → `succeeded` (`reconciled_found`); not found → retried under the same reference (`reconciled_retried`). Operators or a scheduled job run it, never the model.
- **Guarantee, stated precisely:** at most one ticket per approval for this ticket service. It is not a universal exactly-once guarantee for arbitrary external APIs: it relies on the upstream being idempotent on the reference and queryable by it.
- **Checkpoints.** LangGraph's `AsyncPostgresSaver` (`langgraph-checkpoint-postgres` 3.2.0). Tables are created by the schema owner (`python -m agentops_agents setup-checkpoints`) and granted to `agentops_app_rw`. The thread id is derived from, but distinct from, the run id (`thread-<run_id>`). psycopg's async mode cannot use Windows' default event loop, so entry points use `agentops_core.aio.run` (selector loop on Windows).
- **Approval pause.** With `propose_followup=True`, the workflow adds `propose_action` (requests an approval for one ticket about the largest decline), `await_approval` (LangGraph `interrupt`) and `execute_action` (calls the gateway with the approval). The run returns `awaiting_approval`; `resume_task(run_id, approved=…)` continues it, possibly in a new process. The resume value only says whether to try: the gateway still requires the approval to have been granted through `decide`, so a resume cannot forge one. Earlier nodes are not re-run on resume (no model or tool call is repeated). The run deadline applies per invocation.
**Alternatives considered:**
- Keep the ticket write inside the approval transaction — Rejected: hides exactly the failure mode the registry exists for.
- Return the prior result to a retry of a completed approval — Rejected for now: feat-005's contract denies replays (`APPROVAL_ALREADY_USED`); the registry row is where the result lives.
- Sync `PostgresSaver` with a sync graph — Rejected: the LLM gateway and node calls are async.
**Consequences:**
- Positive: concurrent retries, a crash after the external commit, and ambiguous outcomes before or after the commit each end with exactly one ticket and one `succeeded` registry row; an approved run resumes after a restart and writes once.
- Negative / limits: checkpoint tables have no row-level security, so any session of the app login can read any thread's checkpoint, and checkpoints contain the run's evidence text (tenant documents) in the same database; storing references instead of text is a later improvement. The workflow's read tools still bypass the gateway's policy log. Recovery is per tenant and on demand; nothing schedules it yet. No HTTP endpoints for runs or approvals yet.

### D-011: Redacted tracing, one tool path, demo-token feedback and a versioned evaluation corpus

**Date:** 2026-11-19
**Status:** accepted
**Context:** feat-007 (M3.1) needs debuggable runs (correlated, sanitized traces), human feedback, and a versioned evaluation corpus whose results record their provenance, with a failing case traceable to its trace.
**Decision:**
- **Tracing (`packages/telemetry`).** OpenTelemetry spans named per spec 10.1 (`http.request`, `agent.run`, `agent.node`, `llm.generate`, `policy.evaluate`, `approval.wait`, `tool.authorize`, `tool.execute`, `tool.reconcile`, `rag.retrieve`, `eval.case`). Span attributes carry ids, counts and codes only, never prompt, task or document text. Every exporter sits behind `RedactingSpanExporter`, which scrubs attributes, events and status descriptions (provider/Langfuse keys, `CANARY-*`, URL passwords, bearer/basic tokens, `password=`-style pairs, e-mail addresses). A run's spans all carry the run's trace id: the root span joins `RunDetail.trace_id` (also on resume). Langfuse export is OTLP over HTTP, batched, only with `LANGFUSE_ENABLED=true` and keys from the environment; the API refuses to start enabled without keys. Tests use an in-memory exporter behind the same redaction.
- **One tool path (fixes a real access gap).** The evaluation case `access-01` showed that a viewer, who lacks `sales:read`, got sales data through the workflow, because the workflow called its read tools directly and only the gateway checked role permissions. The workflow now runs every read through `ToolGateway.invoke`; gateway denials appear in the run's policy decisions, and every tool call is in `policy_events`. Kept as the regression test `test_viewer_cannot_read_sales_through_the_workflow` and as eval case `access-01`. The principal check is now the run's first recorded policy decision, so every run, including a rejected one, has a policy record (NFR-002).
- **Feedback (`POST /v1/runs/{run_id}/feedback`, migration 0005).** Phase 1 demo identity (spec 9): a configured bearer token (`DEMO_API_TOKEN`, compared in constant time) stands for one configured demo user; no token configured means feedback is disabled (503). Errors are problem details with a `request_id`. `run_id` is a reference, not a foreign key, because runs are not stored as rows yet. `python -m agentops_data export-feedback` exports for review.
- **Evaluation corpus (`datasets/evals/v1`, `packages/evals`).** 50 cases in the spec's split (normal 10, multi-source 8, missing 6, tool/schema 6, injection 8, access 4, reliability 6, budget 2). Workflow cases carry their scripted model turns and explicit expectations; reliability cases are named scenarios (approved write, replay, concurrent retries, crash after commit, uncertain before commit, resume after restart, two gateway injection attempts). Expectations are computed by `build_v1.py` independently of the platform (from `sales.csv` and the document files), and the JSONL file is the reviewed source. The runner records `dataset_version`, `git_sha` (from `GITHUB_SHA` or `.git`, no subprocess), provider, model, `prompt_version` (hash of the two prompts) and `policy_version`; each case runs in an `eval.case` span sharing the run's trace id.
**Alternatives considered:**
- Redact only where attributes are set — Rejected: exception events and status text bypass it; the exporter layer is the backstop.
- Keep the workflow's direct reads and copy the permission check into it — Rejected: two enforcement points drift; one gateway is simpler.
- LLM-as-judge scoring — Deferred: deterministic expectations first (spec 10.2 says judges need calibration before gating).
**Consequences:**
- Positive: 50/50 cases pass in mock mode in CI; changing any of eleven sampled expectations makes its case fail with a precise reason; a failing case's trace id finds its spans.
- Negative / limits: the corpus measures the platform's enforcement and plumbing with scripted model turns, not model quality; hosted-model evaluation is opt-in work for later. Hashing retrieval makes multi-source expectations depend on lexical overlap. The demo token is not authentication for a public deployment. Feedback is not linked to stored runs.
