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

**Not implemented yet.** The repository holds the specification and the development harness; no application code exists and no feature has passed verification. Nothing below claims a working capability until its feature passes `npm run verify-feature`.

## Quick Start

Prerequisites today: Node.js ≥ 18 and Git (Git Bash on Windows for `./init.sh`). From feat-001 on: Python and [uv](https://docs.astral.sh/uv/); from feat-002: Docker.

```bash
./init.sh          # check the environment and print the session brief
npm run check      # run every verification layer
```

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
