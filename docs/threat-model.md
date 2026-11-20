# Threat model

Scope: the Phase 1 platform as built (feat-001 to feat-009), running locally or as a replay-only public demo. Each threat names the control that addresses it and the test that shows the control works. "Residual" is what the control does not cover. Tests are under `testsuite/acceptance/` unless noted; eval cases are in `datasets/evals/v1/cases.jsonl`.

## Assets

- Tenant data: synthetic sales rows, documents and chunks, issues (two tenants, `demo-a` and `demo-b`).
- Restricted documents (board notes, expansion plan), readable only by the admin role.
- The ability to write: sandbox tickets created through approvals.
- Secrets: database passwords, the demo bearer token, provider and Langfuse keys (none needed in mock mode).
- Run records: run details, checkpoints, the policy and execution logs, feedback.

## Trust boundaries

1. Visitor or client → API (demo bearer token for mutations; the replay UI makes no API calls).
2. API / workflow → model provider (mock by default; hosted only with `LLM_MODE` + `ENABLE_LIVE_LLM` + a registered model).
3. Model output → tool gateway (the model proposes; the gateway decides).
4. Tool gateway → PostgreSQL (least-privilege logins, row-level security).
5. Retrieved content → model context (documents and tool results are data, never instructions).
6. Platform → telemetry exporters (redaction before export).

## Threats, controls and evidence

| # | Threat | Control | Evidence |
|---|---|---|---|
| T1 | Injected instructions in a retrieved document make the model act | Tool allowlist and strict argument schemas; writes need a bound approval; citations limited to what the run retrieved | `feat_005/test_injection_and_mcp.py`; eval cases `inject-01`–`inject-08`; replay `injection-demo-b` |
| T2 | Malicious tool result or model output smuggles a tenant or user id | Argument models forbid extra fields; tenant and user come from the trusted call context | `feat_005/test_gateway_reads.py`; eval `tools-03`, `inject-02`, `inject-06` |
| T3 | Model asks for arbitrary SQL (`DROP TABLE`) | No SQL tool exists; `run_sql` is not allowlisted; read-only analytics login; arch-102 bans process spawning | `feat_002/test_readonly_role.py`; eval `tools-01`, `tools-06`, `inject-05` |
| T4 | Cross-tenant read | Row-level security on every tenant table; typed functions filter by tenant too | `feat_002/test_tenant_isolation.py`; `feat_004/test_retrieval.py` |
| T5 | A user reads data their role does not allow | Role permissions in the gateway, which every workflow read uses (D-011); role-filtered retrieval inside the ranking query | `feat_007/test_run_telemetry.py::test_viewer_cannot_read_sales_through_the_workflow`; eval `access-01`, `access-03` |
| T6 | Forged, expired, mutated, replayed or borrowed approval | Approval bound to principal, run, tool, policy version, expiry and SHA-256 of the arguments; consumed with the write | `feat_005/test_approvals.py` |
| T7 | Duplicate or lost writes under retries and crashes | Execution registry, idempotent ticket service, reconciliation by reference | `feat_006/test_execution_registry.py`; eval `reliability-01`–`reliability-05` |
| T8 | A resume forges an approval | The gateway re-checks the approval; the resume value only says "try" | `feat_006/test_checkpoint_resume.py::test_resume_cannot_forge_an_approval` |
| T9 | Secrets or PII in telemetry | Spans carry ids and counts only; every exporter is wrapped in redaction | `feat_007/test_telemetry.py`; canary tests in `feat_001`, `feat_003`, `feat_007` |
| T10 | Provider key committed to the repository | arch-104 forbids key patterns in tracked product files | `npm run check-arch` |
| T11 | Unbounded loops or spend | Limits on model calls, tool calls, graph steps and time; mock by default; daily cap on demo runs | `feat_004/test_abstain_and_limits.py`; `feat_009/test_live_runs.py`; eval `budget-01` |
| T12 | Unauthenticated mutation | Demo bearer token compared in constant time; mutations disabled without it | `feat_007/test_feedback.py`; `feat_009/test_live_runs.py` |
| T13 | Supply-chain compromise of a dependency | 14-day release cooldown (`uv` `exclude-newer`, `npm install --before`); `.pth` review | D-006; lockfiles |
| T15 | One tenant reads or resumes another tenant's paused run | Thread ids carry the tenant; row-level security on the checkpoint tables; tenant-scoped checkpointer connections (D-014) | `feat_010/test_checkpoint_isolation.py` |
| T14 | Public demo leaks data or calls a model | The demo is a static export of sanitized replays; no backend or provider request leaves the browser | `apps/web/e2e/replays.spec.ts` (all requests must stay on localhost); `feat_009/test_replays.py` |

## Residual risks

- The demo bearer token is a single shared credential, not user authentication; it is fit for a local or invite-only demo, not a public live endpoint.
- Checkpoints contain retrieved evidence text; they are isolated per tenant (D-014) but not minimized to references.
- The analytics login could set its own tenant if it could run arbitrary SQL; isolation relies on typed functions plus RLS (D-007).
- Prompt-injection tests show the platform refuses the actions; they do not measure whether a real model resists the text.
- Redaction is pattern-based; secrets in unforeseen formats could pass if code ever put them into spans.
- No rate limiting on the read-only health endpoints; no CSRF protection, since there are no browser sessions (the replay UI is static files).
