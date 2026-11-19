-- Execution registry for external writes (feat-006, D-010).
-- One row per (tenant, tool, idempotency key); the key is derived server-side from the
-- approval, so one approval can reserve one execution. Status moves
-- reserved -> executing -> succeeded | failed | uncertain; uncertain and stale executing rows
-- are reconciled by external_reference before any retry.

CREATE TABLE tool_executions (
    id                 uuid        PRIMARY KEY,
    tenant_id          text        NOT NULL REFERENCES tenants (id),
    run_id             text        NOT NULL,
    principal_id       text        NOT NULL REFERENCES users (id),
    tool_name          text        NOT NULL,
    idempotency_key    text        NOT NULL,
    action_hash        char(64)    NOT NULL,
    approval_id        uuid        REFERENCES approvals (id),
    status             text        NOT NULL
                                   CHECK (status IN ('reserved', 'executing', 'succeeded',
                                                     'failed', 'uncertain')),
    attempt_count      integer     NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    external_reference text        NOT NULL,
    request_json       jsonb       NOT NULL,
    result_json        jsonb,
    error_code         text,
    created_at         timestamptz NOT NULL DEFAULT now(),
    updated_at         timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, tool_name, idempotency_key)
);

CREATE INDEX tool_executions_recovery ON tool_executions (tenant_id, status, updated_at);

ALTER TABLE tool_executions ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON tool_executions
    USING (tenant_id = current_setting('app.tenant_id', true));

-- The gateway reserves and advances executions; it never deletes or rewrites their identity.
GRANT SELECT, INSERT ON tool_executions TO agentops_app_rw;
GRANT UPDATE (status, attempt_count, result_json, error_code, updated_at)
    ON tool_executions TO agentops_app_rw;
