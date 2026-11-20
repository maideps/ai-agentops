-- Per-user run requests for the capped live demo (feat-009, D-013).

CREATE TABLE demo_run_requests (
    id         bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id  text        NOT NULL REFERENCES tenants (id),
    user_id    text        NOT NULL REFERENCES users (id),
    run_id     text        NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX demo_run_requests_user_day ON demo_run_requests (tenant_id, user_id, created_at);

ALTER TABLE demo_run_requests ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON demo_run_requests
    USING (tenant_id = current_setting('app.tenant_id', true));

GRANT SELECT, INSERT ON demo_run_requests TO agentops_app_rw;
