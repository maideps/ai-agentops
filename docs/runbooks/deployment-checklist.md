# Deployment checklist

Two shapes are supported. Prefer the first for anything public.

## A. Public replay demo (recommended)

The demo is a static site. It needs no backend, database, key or model, and keeps working when every other service is asleep (FR-015).

- [ ] Record or refresh replays only from synthetic data: `uv run python -m agentops_evals record-replays` against a local database, then `uv run pytest testsuite/acceptance/feat_009/test_replays.py` (schema, coverage and secret checks).
- [ ] Build: `npm ci --prefix apps/web` then `npm --prefix apps/web run build`; the site is `apps/web/out/`.
- [ ] Verify: `npm --prefix apps/web run e2e` (every request must stay local; screenshots land in `apps/web/test-results/shots/`).
- [ ] Publish `apps/web/out/` to any static host. Nothing else is deployed.
- [ ] Confirm the banner reads "Replay mode" and that the browser's network panel shows only the static host.

## B. Live API (local or invite-only)

Only with an operator who accepts the residual risks in `docs/threat-model.md`.

- [ ] PostgreSQL 17 with pgvector 0.8.0 (or `docker compose up -d --wait postgres`); roles from `infra/postgres/init/` with real passwords (`POSTGRES_PASSWORD`, `ANALYTICS_DB_PASSWORD`, `APP_DB_PASSWORD`).
- [ ] As the schema owner (`DATABASE_URL`): `python -m agentops_data migrate`, `seed`, `python -m agentops_retrieval index`, `python -m agentops_agents setup-checkpoints`.
- [ ] API environment: `APP_DATABASE_URL`, `ANALYTICS_DATABASE_URL`, `DATABASE_URL` (readiness check only), `DEMO_API_TOKEN` (long random value, stored as a secret), `DEMO_TENANT_ID`, `DEMO_USER_ID`, `MAX_REQUESTS_PER_DEMO_USER`, run limits.
- [ ] Keep `LLM_MODE=mock` unless a hosted model is deliberately enabled; hosted models need `LLM_MODE=hosted_free|live_paid`, `ENABLE_LIVE_LLM=true`, a model registered in the capability registry (none is today) and an agreed budget.
- [ ] Use `LLM_MODE=replay` for an API that must never run tasks (POST /v1/runs answers 503).
- [ ] Tracing: leave `LANGFUSE_ENABLED=false`, or set it with `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY` and `LANGFUSE_HOST`; the API refuses to start enabled without keys.
- [ ] Serve with `uv run uvicorn agentops_api.app:create_app --factory --host 127.0.0.1` behind a TLS-terminating proxy; never expose PostgreSQL.
- [ ] Check `GET /health/ready` returns 200 and `{"database": "ok"}`.
- [ ] Schedule `python -m agentops_tools recover --tenant <t>` (for example every 5 minutes) once writes are enabled.
- [ ] Run the evaluation corpus against this environment before opening it: `python -m agentops_evals run` must report 50/50.
