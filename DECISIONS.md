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
