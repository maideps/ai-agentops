-- Tenants, principals, synthetic sales and documents with row-level tenant isolation.
-- Requires the roles created by infra/postgres/init (agentops_readonly).

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE tenants (
    id   text PRIMARY KEY CHECK (id ~ '^[a-z0-9][a-z0-9-]{0,31}$'),
    name text NOT NULL
);

CREATE TABLE roles (
    id          text PRIMARY KEY,
    description text NOT NULL
);

CREATE TABLE role_document_access (
    role_id      text NOT NULL REFERENCES roles (id),
    access_label text NOT NULL CHECK (access_label IN ('public', 'internal', 'restricted')),
    PRIMARY KEY (role_id, access_label)
);

CREATE TABLE users (
    id           text PRIMARY KEY,
    tenant_id    text NOT NULL REFERENCES tenants (id),
    display_name text NOT NULL,
    role_id      text NOT NULL REFERENCES roles (id)
);

CREATE TABLE business_sales (
    tenant_id    text          NOT NULL REFERENCES tenants (id),
    product_id   integer       NOT NULL,
    product_name text          NOT NULL,
    region       text          NOT NULL,
    quarter      text          NOT NULL CHECK (quarter ~ '^[0-9]{4}-Q[1-4]$'),
    revenue      numeric(14, 2) NOT NULL CHECK (revenue >= 0),
    units        integer       NOT NULL CHECK (units >= 0),
    PRIMARY KEY (tenant_id, product_id, region, quarter)
);

CREATE TABLE documents (
    id             text        PRIMARY KEY,
    tenant_id      text        NOT NULL REFERENCES tenants (id),
    title          text        NOT NULL,
    source_uri     text        NOT NULL,
    access_label   text        NOT NULL CHECK (access_label IN ('public', 'internal', 'restricted')),
    content_sha256 char(64)    NOT NULL,
    version        integer     NOT NULL DEFAULT 1 CHECK (version >= 1),
    created_at     timestamptz NOT NULL DEFAULT now(),
    updated_at     timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE document_chunks (
    id          text     PRIMARY KEY,
    document_id text     NOT NULL REFERENCES documents (id) ON DELETE CASCADE,
    tenant_id   text     NOT NULL REFERENCES tenants (id),
    chunk_index integer  NOT NULL CHECK (chunk_index >= 0),
    text        text     NOT NULL,
    text_sha256 char(64) NOT NULL,
    UNIQUE (document_id, chunk_index)
);

CREATE INDEX business_sales_tenant_quarter ON business_sales (tenant_id, quarter);
CREATE INDEX documents_tenant ON documents (tenant_id);
CREATE INDEX document_chunks_tenant_document ON document_chunks (tenant_id, document_id);

-- Row-level security: a non-owner role sees only rows of the tenant set for its transaction
-- with set_config('app.tenant_id', ..., true). No tenant set means no rows.
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE business_sales ENABLE ROW LEVEL SECURITY;
ALTER TABLE documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE document_chunks ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON users
    USING (tenant_id = current_setting('app.tenant_id', true));
CREATE POLICY tenant_isolation ON business_sales
    USING (tenant_id = current_setting('app.tenant_id', true));
CREATE POLICY tenant_isolation ON documents
    USING (tenant_id = current_setting('app.tenant_id', true));
CREATE POLICY tenant_isolation ON document_chunks
    USING (tenant_id = current_setting('app.tenant_id', true));

-- Read-only access for analytics; no write privilege is granted to anyone but the owner.
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO agentops_readonly;
GRANT SELECT ON tenants, roles, role_document_access, users, business_sales, documents,
    document_chunks TO agentops_readonly;
