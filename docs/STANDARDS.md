# Project Standards

Single source of truth for this project's coding standards and non-negotiable rules. Agents and reviewers check every change against this file. The requirements themselves live in [`ARCHITECTURE_AND_REQUIREMENTS.md`](ARCHITECTURE_AND_REQUIREMENTS.md) (authoritative); the milestone breakdown lives in [`CLAUDE_CODE_HANDOFF.md`](CLAUDE_CODE_HANDOFF.md). The harness workflow (one active feature, verify-feature, session notes) lives in the root `AGENTS.md`.

Each rule names what enforces it today. "Review" means only a human or the `review` skill catches it; turn it into a check when one becomes possible.

## Core Principles (non-negotiable)

- **One vertical slice at a time.** Work on exactly one feature from `feature_list.json`, in dependency order, starting with feat-001 (M0.1). No big-bang scaffolding, no speculative integrations, no empty directories created for appearance. *Enforced by: `npm run activate` (WIP=1, dependency order).*
- **Inspect before assuming.** Do not assume project files, installed packages or running infrastructure exist. *Enforced by: review.*
- **Mock-first, no surprise spend.** `LLM_MODE=mock` is the default and stays authoritative even when a developer machine has real keys. Never call a commercial LLM API unless the owner explicitly opts in; CI always uses mocks; tests must not reach a provider network. *Enforced by: review now; a network-blocking test fixture from feat-003 (M1.1).*
- **No secrets or private data in output.** Never disclose or log API keys, secrets, PII, raw customer data or private retrieved documents — not in code, logs, traces, fixtures, PRs or screenshots. *Enforced by: arch-104 (key patterns in tracked files); redaction canary tests from feat-007 (M3.1).*
- **Deny by default.** Typed tool contracts, ACLs, server-side authorization, approved write actions and explicit runtime limits. The model may propose a tool call; it never authorizes one. *Enforced by: security tests from feat-005 (M2.1).*
- **No privileged model capabilities.** The LLM cannot bypass policy checks, issue arbitrary SQL writes, execute shell commands or reach arbitrary external URLs. *Enforced by: arch-102 (no process spawning in product code), FR-004 DB-role tests, review.*
- **Side effects need idempotency and reconciliation.** Every external write has an idempotency key, an execution-registry row and a reconciliation path, with tests. Graph checkpointing alone does not make actions exactly once. *Enforced by: reliability tests from feat-006 (M2.2).*
- **Prescribed stack.** LangGraph for orchestration and durable state, PostgreSQL/pgvector for seeded synthetic data, MCP for first-party tools, LiteLLM SDK behind the `LLMProvider` port, OpenTelemetry/Langfuse for optional sanitized traces. *Enforced by: arch-101 (LiteLLM only inside `packages/llm/`), review.*
- **Honest claims.** Code is typed, testable and versioned. No unverified claims about benchmarks, safety or security; targets in the spec are proposals, not results. *Enforced by: verify-feature evidence, `readme-review` skill.*
- **No unapproved actions.** Use official, version-matched documentation. Do not run destructive commands, provision cloud infrastructure, connect accounts or install from `curl | bash` without explicit owner approval. *Enforced by: review; Claude Code permission prompts.*

## Session Start (overrides `./init.sh` for now, D-004)

**Do not run `./init.sh` or `npm run setup`**: with this Python project they would `pip install` into the system Python. Start each session with:

```bash
uv sync                                     # install from uv.lock into .venv
docker compose up -d --wait postgres         # Docker Desktop must be running
node scripts/framework-check.mjs brief      # the session brief init.sh would print
npm run check                               # full verification
```

Run `node scripts/framework-check.mjs selftest` when the harness self-tests are needed (for example after `harness-upgrade`).

## Sequence for Every Feature

Runs inside the harness loop in `AGENTS.md` (activate → implement → commit → `verify-feature` → session note):

1. Read `ARCHITECTURE_AND_REQUIREMENTS.md` and `CLAUDE_CODE_HANDOFF.md` (at least the sections the feature cites) and check `git status`.
2. Propose an acceptance-test-driven plan for the **next smallest feature only**.
3. Explain the relevant requirement ids and architecture decisions; record new decisions in `DECISIONS.md`.
4. Implement code and tests; run the relevant checks.
5. Report changed files, commands executed, pass/fail evidence, costs and network activity, and the next feature.

## Phase 1 Focus

One working task: synthetic sales + evidence → grounded report → authorized proposed action. Build reliable tooling, checkpointing, approval and idempotency around that single task first. Only then (feat-008, M4.1) compare three specialists (Research / Data Analyst / Reporting) against the single-workflow baseline, keeping the simpler design unless measurements favor the specialists. Replay mode must keep working without any hosted LLM.

## Language and Tooling

- **Python** (version pinned in `.python-version` from feat-001) with **uv** for reproducible dependencies (`uv.lock` committed).
- **FastAPI + Pydantic** for the API; typed Python throughout.
- **Ruff** for lint and format (`uv run ruff check .`, `uv run ruff format --check .`). Enable at least `E`, `F`, `I`, `B`, `UP`, `S110`, `BLE001`, `E722` so swallowed and blind exceptions fail lint alongside arch-103.
- **mypy** in strict mode over product code and `testsuite/` (`uv run mypy`, targets in `[tool.mypy] files`; add each new package there).
- **pytest** (`uv run pytest`) with markers `integration` (needs local Postgres), `live` (real provider; never in default CI).
- **Dependency cooldown (D-006):** `[tool.uv] exclude-newer` keeps the lock to releases about 14 days old. Bump the date only in a dedicated commit, review the `uv lock` diff, and check `.venv` for unexpected `.pth` files.
- **Node.js ≥ 18** only for the harness runtime, and later the Next.js UI in `apps/web/`.
- **Docker Compose** for local PostgreSQL + pgvector (from feat-002).

The harness's `npm run lint`/`test`/`typecheck` scripts check harness state only. Python checks are declared on each feature's layers in `feature_list.json` and, once `pyproject.toml` exists (feat-001), chained into the `package.json` scripts with `&&`, so `npm run check` runs them too (see the Usage section of the root README).

## Testing Discipline

- New behavior starts with a failing acceptance test written from the feature's declared `behavior`. A bug starts with a failing regression test.
- Product tests live in `testsuite/`, not `tests/` (`tests/` holds the harness's own self-tests and is replaced on harness upgrades; see D-002):
  - `testsuite/acceptance/feat_NNN/` — the declared behavior of one feature
  - `testsuite/unit/`, `testsuite/contracts/`, `testsuite/integration/`, `testsuite/security/`, `testsuite/reliability/`, `testsuite/evals/`, `testsuite/live/`
- Default suite: `uv run pytest testsuite -m "not live and not integration"` — no network, no keys, no Docker. Keep it under about two minutes.
- Integration suite: Postgres via Docker Compose, `-m integration`.
- Security and reliability fixtures (prompt injection, cross-tenant access, forged/mutated/replayed approvals, duplicate writes, crash after commit) are versioned and run in default CI.
- No swallowed exceptions (`except Exception: pass`), no unbounded retries, no silent fallback to unsafe behavior.

## Naming and Structure

- Strict boundaries: API → application services → domain ports; infrastructure adapters implement the ports. Domain code imports no framework or provider SDK.
- Layout (added only when a feature needs it): `apps/api`, `apps/web`, `packages/{core,agents,llm,retrieval,tools,telemetry,evals}`, `testsuite/`, `datasets/synthetic/`, `fixtures/{llm,replays,tool_results}/`.
- Typed errors with stable codes (`MODEL_CAPABILITY_UNSUPPORTED`, `RATE_LIMITED`, `BUDGET_EXCEEDED`, …); API errors as problem details (`code`, `message`, `request_id`) without stack traces or secrets.
- Feature ids `feat-NNN`; each feature's name starts with its milestone (`M0.1`, `M1.2`, …) and its behavior cites requirement ids (`FR-001`, `NFR-004`).

## Commit and Review Standards

- One logical operation per commit; the message explains why. Commit before `npm run verify-feature`, then commit the state shard and trail it writes.
- Every PR/feature links its requirement ids and passes the review checklist in `CLAUDE_CODE_HANDOFF.md` §8: no privileged path bypasses the policy gateway, writes are idempotent, provider behavior stays behind the port, trace ids and error codes are actionable, secrets/PII redacted, limits tested, no paid call in CI.
- Each new error category caught in review becomes a check (`forbid` rule in `.harness/arch-rules.json`, a test, or a lint rule) in the same commit as the fix.

## Documentation Standards

- Update docs in the same commit as the code: README (what the app does now), ADRs (`DECISIONS.md`, expanded in `docs/decisions/` with context, alternatives, decision, consequences, reversal conditions), threat model, test evidence and requirement traceability.
- `ARCHITECTURE_AND_REQUIREMENTS.md` is the source of truth. If documents diverge, update it first, then the handoff, then the blueprint PDF kept locally in `.base/` (not in the repository).
- Final report of each feature: changed files, commands run, pass/fail evidence, costs/network activity, next ticket.
