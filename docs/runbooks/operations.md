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

## Reviewing feedback and decisions

- Feedback: `uv run python -m agentops_data export-feedback --tenant demo-a` (JSON lines).
- Policy decisions and executions for a run (as the schema owner): `SELECT * FROM policy_events WHERE run_id = '<run>' ORDER BY id;` and `SELECT * FROM tool_executions WHERE run_id = '<run>';`.
