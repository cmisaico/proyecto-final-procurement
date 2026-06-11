-- ============================================================
-- Autonomous Procurement Intelligence Platform — DDL
-- ============================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ------------------------------------------------------------
-- ENUMS
-- ------------------------------------------------------------

CREATE TYPE document_status AS ENUM (
    'uploaded', 'processing', 'processed', 'failed'
);

CREATE TYPE tender_status AS ENUM (
    'draft', 'active', 'analyzed', 'closed'
);

CREATE TYPE requirement_type AS ENUM (
    'document', 'technical', 'financial', 'legal',
    'deadline', 'restriction', 'other'
);

CREATE TYPE requirement_priority AS ENUM (
    'mandatory', 'optional'
);

-- ------------------------------------------------------------
-- USERS
-- ------------------------------------------------------------

CREATE TABLE IF NOT EXISTS users (
    id          VARCHAR(36)  PRIMARY KEY DEFAULT uuid_generate_v4()::text,
    email       VARCHAR(255) NOT NULL UNIQUE,
    full_name   VARCHAR(255) NOT NULL,
    is_active   BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMP    NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_users_email ON users (email);

-- ------------------------------------------------------------
-- PROJECTS
-- ------------------------------------------------------------

CREATE TABLE IF NOT EXISTS projects (
    id          VARCHAR(36)  PRIMARY KEY DEFAULT uuid_generate_v4()::text,
    user_id     VARCHAR(36)  NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name        VARCHAR(255) NOT NULL,
    description TEXT,
    created_at  TIMESTAMP    NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_projects_user ON projects (user_id);

-- ------------------------------------------------------------
-- TENDERS
-- ------------------------------------------------------------

CREATE TABLE IF NOT EXISTS tenders (
    id          VARCHAR(36)     PRIMARY KEY DEFAULT uuid_generate_v4()::text,
    project_id  VARCHAR(36)     NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    title       VARCHAR(500)    NOT NULL,
    description TEXT,
    status      tender_status   NOT NULL DEFAULT 'draft',
    deadline    TIMESTAMP,
    created_at  TIMESTAMP       NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMP       NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_tenders_project ON tenders (project_id);
CREATE INDEX IF NOT EXISTS idx_tenders_status  ON tenders (status);

-- ------------------------------------------------------------
-- DOCUMENTS
-- ------------------------------------------------------------

CREATE TABLE IF NOT EXISTS documents (
    id                VARCHAR(36)     PRIMARY KEY DEFAULT uuid_generate_v4()::text,
    tender_id         VARCHAR(36)     NOT NULL REFERENCES tenders(id) ON DELETE CASCADE,
    filename          VARCHAR(500)    NOT NULL,
    original_filename VARCHAR(500)    NOT NULL,
    minio_path        VARCHAR(1000)   NOT NULL,
    file_size         BIGINT          NOT NULL DEFAULT 0,
    mime_type         VARCHAR(100)    NOT NULL DEFAULT 'application/pdf',
    status            document_status NOT NULL DEFAULT 'uploaded',
    page_count        INTEGER         NOT NULL DEFAULT 0,
    extracted_text    TEXT,
    created_at        TIMESTAMP       NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMP       NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_documents_tender ON documents (tender_id);
CREATE INDEX IF NOT EXISTS idx_documents_status ON documents (status);

-- ------------------------------------------------------------
-- CHUNKS
-- ------------------------------------------------------------

CREATE TABLE IF NOT EXISTS chunks (
    id          VARCHAR(36) PRIMARY KEY DEFAULT uuid_generate_v4()::text,
    document_id VARCHAR(36) NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    content     TEXT        NOT NULL,
    chunk_index INTEGER     NOT NULL,
    page_number INTEGER,
    char_start  INTEGER     NOT NULL DEFAULT 0,
    char_end    INTEGER     NOT NULL DEFAULT 0,
    qdrant_id   VARCHAR(36),
    created_at  TIMESTAMP   NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_chunks_document  ON chunks (document_id);
CREATE INDEX IF NOT EXISTS idx_chunks_qdrant_id ON chunks (qdrant_id);

-- ------------------------------------------------------------
-- REQUIREMENTS
-- ------------------------------------------------------------

CREATE TABLE IF NOT EXISTS requirements (
    id          VARCHAR(36)            PRIMARY KEY DEFAULT uuid_generate_v4()::text,
    tender_id   VARCHAR(36)            NOT NULL REFERENCES tenders(id) ON DELETE CASCADE,
    document_id VARCHAR(36)            NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    type        requirement_type       NOT NULL,
    priority    requirement_priority   NOT NULL DEFAULT 'mandatory',
    description TEXT                   NOT NULL,
    raw_text    TEXT,
    deadline    TIMESTAMP,
    created_at  TIMESTAMP              NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_requirements_tender ON requirements (tender_id);
CREATE INDEX IF NOT EXISTS idx_requirements_type   ON requirements (type);

-- ------------------------------------------------------------
-- Trigger: auto-update updated_at
-- ------------------------------------------------------------

CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_tenders_updated_at
    BEFORE UPDATE ON tenders
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER trg_documents_updated_at
    BEFORE UPDATE ON documents
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ------------------------------------------------------------
-- Seed: default user and project for demo
-- ------------------------------------------------------------

INSERT INTO users (id, email, full_name)
VALUES ('00000000-0000-0000-0000-000000000001', 'demo@procurement.ai', 'Demo User')
ON CONFLICT (email) DO NOTHING;

INSERT INTO projects (id, user_id, name, description)
VALUES (
    '00000000-0000-0000-0000-000000000002',
    '00000000-0000-0000-0000-000000000001',
    'Proyecto Demo',
    'Proyecto de demostración para análisis de licitaciones'
) ON CONFLICT DO NOTHING;

INSERT INTO tenders (id, project_id, title, status)
VALUES (
    '00000000-0000-0000-0000-000000000003',
    '00000000-0000-0000-0000-000000000002',
    'Licitación Demo',
    'draft'
) ON CONFLICT DO NOTHING;
