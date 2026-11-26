# Operations runbook

Commands assume the repository root, `uv sync` done, Docker running, and these variables:

```bash
export DATABASE_URL=postgresql://agentops:change-me@127.0.0.1:15432/agentops                        # schema owner
export ANALYTICS_DATABASE_URL=postgresql://agentops_analytics:change-me-analytics@127.0.0.1:15432/agentops
export APP_DATABASE_URL=postgresql://agentops_app:change-me-app@127.0.0.1:15432/agentops
```

## Start, upgrade, reset

| Task | Command |
|---|---|
| Start PostgreSQL | `docker compose up -d --wait postgres` |
| Apply new migrations | `uv run python -m agentops_data migrate` |
| Load synthetic data (clears runtime rows too) | `uv run python -m agentops_data seed` then `uv run python -m agentops_retrieval index` |
| Create or upgrade checkpoint tables | `uv run python -m agentops_agents setup-checkpoints` |
| Recreate the database from scratch (destroys local data) | `docker compose down -v` then the four commands above |

The role setup in `infra/postgres/init/` runs only on a new volume; after changing it, recreate the volume.

## Checks

| Question | Command |
|---|---|
| Is the API ready? | `curl http://127.0.0.1:8000/health/ready` (503 with `"database": "failed"` means PostgreSQL is unreachable) |
| Does everything still pass? | `npm run check`, then `uv run pytest testsuite -q -m integration` |
| Does the platform still enforce its rules? | `uv run python -m agentops_evals run` (expects 50/50; prints the trace id of any failure) |
| Does the replay UI still work offline? | `npm --prefix apps/web run e2e` |

## Incidents

**A ticket write ended `EXECUTION_UNCERTAIN`, or a process died mid-write.** Run `uv run python -m agentops_tools recover --tenant <tenant>`. Each stuck execution is looked up by its `SBX-…` reference first: `reconciled_found` means it already happened, `reconciled_retried` means it was written now. Never resubmit the approval by hand; a second approval would create a second ticket.

**A run is stuck in `awaiting_approval`.** The requesting user calls `POST /v1/runs/{run_id}/approvals/{approval_id}` with `{"decision": "approve"}` or `"reject"` (the approval id is in the run's `proposed_action`; `GET /v1/runs/{run_id}` shows it). Approvals expire after 15 minutes; an expired one answers 409, so start a new run.

**Demo users hit `QUOTA_EXCEEDED`.** The cap is `MAX_REQUESTS_PER_DEMO_USER` runs per user per UTC day, counted in `demo_run_requests`. Raise the setting or wait for the next UTC day; do not delete rows in production.

**Suspected secret in telemetry.** Disable export (`LANGFUSE_ENABLED=false`), rotate the secret, find the span by trace id, and add the pattern to `agentops_telemetry/redaction.py` with a test in `feat_007/test_telemetry.py`.

**Rotate the demo token.** Set a new `DEMO_API_TOKEN` and restart the API; old tokens stop working immediately.

## Manual hosted evaluation

Do not run these commands without owner approval of the two command budgets and a
`GEMINI_API_KEY` supplied through the shell or a secret store. Never paste a key into chat,
commit it, or include it in recorded output. Default commands and CI stay mock-only.

Set `LLM_MODE=hosted_free` (only after checking the provider's free allowance/terms) or
`live_paid`, `ENABLE_LIVE_LLM=true`, and the existing database URLs. For the HTTP API also
set `LLM_MODEL=gemini/gemini-3.5-flash-lite` and a positive `LLM_BUDGET_USD`; its default
is zero, so flags and a key alone cannot spend.

Example command caps below are **not approval** and may exhaust before all cases finish:

```bash
uv run python -m agentops_evals run --live --budget-usd 10 --out benchmarks/evals/v1.1/live/evals-live.json
uv run python -m agentops_evals benchmark --live --budget-usd 30 --out-dir benchmarks/orchestration/v1/live-evals-v1.1
```

Each command's explicit cap covers both each run and the complete batch. Each dispatched
call reserves all 1,048,576 input tokens plus the requested maximum output; at the default
1,024 output tokens this is USD 0.3171328. Reservations are never refunded, including after
failures. No SDK retries are permitted; the adapter itself retries a 503 or connection error at
most twice (feat-015), and each attempt reserves again, so a cap that covers every first attempt
(about USD 78.33 corpus, USD 156.66 benchmark) can still stop late cases after many retries. Use a provider-side account cap too: SDK prices/ceilings are
external assumptions, and these counters do not survive a process restart.

The corpus writes every result (including failures) and exits 1 when any expectation fails.
In live mode each workflow case is also scored by its `live` expectation (D-018): the summary line
prints `live outcomes X/Y (N unscored)` and each result records its error codes and abstain reason.
The live benchmark writes `results-live.json` and `REPORT.md` under
`benchmarks/orchestration/v1/live/` by default, leaving mock artifacts unchanged, and also
exits 1 on failed cases. JSON records dataset, commit, model, prompt version, reported usage
cost and reservation totals. Costs use returned usage at bundled LiteLLM prices, not
invoices; a timeout can have unknown actual spend covered only by its retained reservation.
Only workflow cases use the hosted model; gateway/reliability scenarios remain deterministic.
Some expectations assume scripted model errors or trajectories and may fail live: preserve
them, inspect the trace ids, and do not present the pass rate as a model-quality score.

Commit code before collecting live evidence so `git_sha` names the tested implementation.
Record command caps, observed costs, failures, model/pricing version and the report paths
in the session note; only then close feat-012. Tokenizer downloads on the first Gemini call
are expected (D-005). Return `LLM_MODE` to mock and `ENABLE_LIVE_LLM` to false afterward.

## Reviewing feedback and decisions

- Feedback: `uv run python -m agentops_data export-feedback --tenant demo-a` (JSON lines).
- Policy decisions and executions for a run (as the schema owner): `SELECT * FROM policy_events WHERE run_id = '<run>' ORDER BY id;` and `SELECT * FROM tool_executions WHERE run_id = '<run>';`.
