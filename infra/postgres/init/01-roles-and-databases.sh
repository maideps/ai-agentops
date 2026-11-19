#!/bin/sh
# Runs once, when the data volume is first created (docker-entrypoint-initdb.d).
# Roles are cluster-wide; migrations grant table privileges to the NOLOGIN group roles.
set -eu

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  -v analytics_pw="$ANALYTICS_DB_PASSWORD" -v app_pw="$APP_DB_PASSWORD" <<'SQL'
-- Group role that holds read-only grants; cannot log in.
CREATE ROLE agentops_readonly NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
-- Group role for the few writes the tool gateway performs (approvals, sandbox tickets, policy log).
CREATE ROLE agentops_app_rw NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
-- Login role used for analytics queries; inherits only the read-only grants.
CREATE ROLE agentops_analytics LOGIN PASSWORD :'analytics_pw'
  NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS INHERIT IN ROLE agentops_readonly;
-- Login role used by the tool gateway: reads plus the gateway's narrow writes.
CREATE ROLE agentops_app LOGIN PASSWORD :'app_pw'
  NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS INHERIT IN ROLE agentops_readonly, agentops_app_rw;
-- Separate database for the integration tests, so they never touch development data.
CREATE DATABASE agentops_test OWNER agentops;
SQL
