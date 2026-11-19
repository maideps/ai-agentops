-- Human feedback per run (FR-014, feat-007). Runs are not persisted as rows yet, so run_id is
-- a reference, not a foreign key; eval_case_id links feedback to the evaluation corpus.

CREATE TABLE run_feedback (
    id           uuid        PRIMARY KEY,
    tenant_id    text        NOT NULL REFERENCES tenants (id),
    run_id       text        NOT NULL CHECK (run_id ~ '^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$'),
    user_id      text        NOT NULL REFERENCES users (id),
    rating       text        NOT NULL CHECK (rating IN ('up', 'down')),
    comment      text        CHECK (char_length(comment) <= 500),
    eval_case_id text,
    created_at   timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX run_feedback_tenant_run ON run_feedback (tenant_id, run_id);

ALTER TABLE run_feedback ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON run_feedback
    USING (tenant_id = current_setting('app.tenant_id', true));

GRANT SELECT, INSERT ON run_feedback TO agentops_app_rw;
