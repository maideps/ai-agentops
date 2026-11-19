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
- Reversal: once an upstream harness release handles uv, run `harness-upgrade`, confirm `./init.sh` uses `uv sync`, and mark this decision superseded.
