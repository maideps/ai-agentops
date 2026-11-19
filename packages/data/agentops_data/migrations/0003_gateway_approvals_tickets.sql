-- Tool gateway: role permissions, issue fixtures, approvals bound to an action hash,
-- sandbox tickets and an append-only policy decision log (feat-005, D-009).
-- Requires agentops_app_rw from infra/postgres/init.

CREATE TABLE role_permissions (
    role_id    text NOT NULL REFERENCES roles (id),
    permission text NOT NULL CHECK (permission ~ '^[a-z]+:(read|write)$'),
    PRIMARY KEY (role_id, permission)
);

CREATE TABLE issues (
    id        text   PRIMARY KEY,
    tenant_id text   NOT NULL REFERENCES tenants (id),
    title     text   NOT NULL,
    body      text   NOT NULL,
    state     text   NOT NULL CHECK (state IN ('open', 'closed')),
    labels    text[] NOT NULL DEFAULT '{}'
);

CREATE TABLE approvals (
    id             uuid        PRIMARY KEY,
    tenant_id      text        NOT NULL REFERENCES tenants (id),
    run_id         text        NOT NULL,
    principal_id   text        NOT NULL REFERENCES users (id),
    tool_name      text        NOT NULL,
    action_hash    char(64)    NOT NULL,
    policy_version text        NOT NULL,
    status         text        NOT NULL DEFAULT 'pending'
                               CHECK (status IN ('pending', 'approved', 'rejected', 'consumed')),
    expires_at     timestamptz NOT NULL,
    decided_by     text        REFERENCES users (id),
    decided_at     timestamptz,
    consumed_at    timestamptz,
    created_at     timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE sandbox_tickets (
    id           text        PRIMARY KEY,
    tenant_id    text        NOT NULL REFERENCES tenants (id),
    approval_id  uuid        NOT NULL UNIQUE REFERENCES approvals (id),
    run_id       text        NOT NULL,
    created_by   text        NOT NULL REFERENCES users (id),
    title        text        NOT NULL,
    description  text        NOT NULL,
    priority     text        NOT NULL CHECK (priority IN ('low', 'medium', 'high')),
    product_id   integer,
    created_at   timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE policy_events (
    id             bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id      text        NOT NULL,
    run_id         text        NOT NULL,
    principal_id   text        NOT NULL,
    event_type     text        NOT NULL
                               CHECK (event_type IN ('tool_call', 'approval_request', 'approval_decision')),
    tool_name      text        NOT NULL,
    decision       text        NOT NULL CHECK (decision IN ('allow', 'deny')),
    reason_code    text        NOT NULL,
    policy_version text        NOT NULL,
    action_hash    char(64),
    approval_id    uuid,
    created_at     timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX approvals_tenant_run ON approvals (tenant_id, run_id);
CREATE INDEX policy_events_tenant_run ON policy_events (tenant_id, run_id);

ALTER TABLE issues ENABLE ROW LEVEL SECURITY;
ALTER TABLE approvals ENABLE ROW LEVEL SECURITY;
ALTER TABLE sandbox_tickets ENABLE ROW LEVEL SECURITY;
ALTER TABLE policy_events ENABLE ROW LEVEL SECURITY;

-- FOR ALL policies: USING filters reads, and the same expression is the WITH CHECK for writes,
-- so a scoped connection can only write rows of its own tenant.
CREATE POLICY tenant_isolation ON issues
    USING (tenant_id = current_setting('app.tenant_id', true));
CREATE POLICY tenant_isolation ON approvals
    USING (tenant_id = current_setting('app.tenant_id', true));
CREATE POLICY tenant_isolation ON sandbox_tickets
    USING (tenant_id = current_setting('app.tenant_id', true));
CREATE POLICY tenant_isolation ON policy_events
    USING (tenant_id = current_setting('app.tenant_id', true));

GRANT SELECT ON role_permissions, issues TO agentops_readonly;

-- The gateway's writes, and nothing else: no DELETE anywhere, no UPDATE of tickets or the log.
GRANT SELECT, INSERT ON approvals, sandbox_tickets, policy_events TO agentops_app_rw;
GRANT UPDATE (status, decided_by, decided_at, consumed_at) ON approvals TO agentops_app_rw;
