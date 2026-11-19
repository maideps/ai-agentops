# Product Overview

**Before working on this project, read [`STANDARDS.md`](STANDARDS.md) (non-negotiable rules) and [`ARCHITECTURE_AND_REQUIREMENTS.md`](ARCHITECTURE_AND_REQUIREMENTS.md) (authoritative requirements).** [`CLAUDE_CODE_HANDOFF.md`](CLAUDE_CODE_HANDOFF.md) is the milestone guide; its milestones are the features in `feature_list.json`.

## Purpose

AI AgentOps is a portfolio-grade, provider-agnostic, security-first agentic platform. It analyzes synthetic business data, retrieves attributable evidence, and proposes narrowly authorized actions that only run after human approval. It must be measurable, resumable, cheap to test (mock-first, no paid API by default) and demonstrably safe within a documented threat model.

## Primary Users

- **Business analyst** (authorized, tenant-scoped): submits tasks, reviews cited reports, approves or rejects proposed actions.
- **Reviewer / hiring manager**: explores replayed synthetic runs, traces, tests and evaluation results without credentials.
- **Operator / owner**: configures providers, budgets and live-mode opt-in.

## Key User Flows

1. The analyst asks: "Analyze quarterly sales, identify the three largest declines, consult relevant company policies, prepare a cited executive summary, and propose a follow-up ticket."
2. The platform retrieves only documents the analyst may see, runs constrained read-only analytics, and produces a grounded, cited report — or abstains when evidence is missing.
3. Before any write, the run pauses for approval. The approval is bound to the principal, action hash, policy version, expiry and run.
4. The approved ticket is created exactly once in a sandbox, even under retries or a crash, and the run records its outcome, policy decisions and trace id.
5. A visitor opens the replay demo and explores recorded synthetic runs with no model access.

## Non-Goals (Phase 1)

Unrestricted web browsing, arbitrary SQL generation or execution, shell or code execution by agents, autonomous messaging, production customer data, unbounded delegation, a full OAuth connector ecosystem, Kubernetes, fine-tuning, local LLMs/GPUs, and any claim of enterprise-grade uptime or universal safety.

## Product Constraints

- No local GPU or local LLM. Default `LLM_MODE=mock` with zero paid model calls; live inference needs `ENABLE_LIVE_LLM=true`, a supported model, a secret and an explicit persistent budget.
- Synthetic data only, for two synthetic tenants.
- The public demo is replay-first and must work when providers, quotas or free-tier hosting are unavailable.
- Harness operations require Node.js 18 or newer; the product is Python (uv) with a later Next.js UI.
