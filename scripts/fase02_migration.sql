-- ============================================================
-- FASE 2 — Multi-Agent Compliance System — Migration
-- ============================================================

-- ------------------------------------------------------------
-- ENUMS nuevos
-- ------------------------------------------------------------

DO $$ BEGIN
    CREATE TYPE workflow_status AS ENUM ('pending','running','completed','failed');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE agent_status AS ENUM ('pending','running','completed','failed','skipped');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE risk_level AS ENUM ('low','medium','high','critical');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- ------------------------------------------------------------
-- WORKFLOW EXECUTIONS
-- ------------------------------------------------------------

CREATE TABLE IF NOT EXISTS workflow_executions (
    id              VARCHAR(36)      PRIMARY KEY DEFAULT uuid_generate_v4()::text,
    tender_id       VARCHAR(36)      NOT NULL REFERENCES tenders(id) ON DELETE CASCADE,
    correlation_id  VARCHAR(36)      NOT NULL UNIQUE,
    status          workflow_status  NOT NULL DEFAULT 'pending',
    input_data      JSONB,
    started_at      TIMESTAMP        NOT NULL DEFAULT NOW(),
    completed_at    TIMESTAMP,
    error_message   TEXT
);

CREATE INDEX IF NOT EXISTS idx_workflow_tender     ON workflow_executions (tender_id);
CREATE INDEX IF NOT EXISTS idx_workflow_status     ON workflow_executions (status);
CREATE INDEX IF NOT EXISTS idx_workflow_correlation ON workflow_executions (correlation_id);

-- ------------------------------------------------------------
-- AGENT RUNS
-- ------------------------------------------------------------

CREATE TABLE IF NOT EXISTS agent_runs (
    id              VARCHAR(36)     PRIMARY KEY DEFAULT uuid_generate_v4()::text,
    workflow_id     VARCHAR(36)     NOT NULL REFERENCES workflow_executions(id) ON DELETE CASCADE,
    agent_name      VARCHAR(100)    NOT NULL,
    status          agent_status    NOT NULL DEFAULT 'pending',
    input_data      JSONB,
    output_data     JSONB,
    guardrail_score FLOAT,
    started_at      TIMESTAMP       NOT NULL DEFAULT NOW(),
    completed_at    TIMESTAMP,
    error_message   TEXT
);

CREATE INDEX IF NOT EXISTS idx_agent_runs_workflow ON agent_runs (workflow_id);
CREATE INDEX IF NOT EXISTS idx_agent_runs_name     ON agent_runs (agent_name);
CREATE INDEX IF NOT EXISTS idx_agent_runs_status   ON agent_runs (status);

-- ------------------------------------------------------------
-- AGENT RESULTS (detailed structured output)
-- ------------------------------------------------------------

CREATE TABLE IF NOT EXISTS agent_results (
    id           VARCHAR(36) PRIMARY KEY DEFAULT uuid_generate_v4()::text,
    agent_run_id VARCHAR(36) NOT NULL REFERENCES agent_runs(id) ON DELETE CASCADE,
    result_type  VARCHAR(100) NOT NULL,
    data         JSONB        NOT NULL,
    created_at   TIMESTAMP    NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_agent_results_run ON agent_results (agent_run_id);

-- ------------------------------------------------------------
-- COMPLIANCE REPORTS
-- ------------------------------------------------------------

CREATE TABLE IF NOT EXISTS compliance_reports (
    id               VARCHAR(36)  PRIMARY KEY DEFAULT uuid_generate_v4()::text,
    workflow_id      VARCHAR(36)  NOT NULL REFERENCES workflow_executions(id) ON DELETE CASCADE,
    tender_id        VARCHAR(36)  NOT NULL REFERENCES tenders(id) ON DELETE CASCADE,
    compliance_score FLOAT        NOT NULL DEFAULT 0,
    risk_level       risk_level   NOT NULL DEFAULT 'medium',
    issues           JSONB        NOT NULL DEFAULT '[]',
    recommendations  JSONB        NOT NULL DEFAULT '[]',
    created_at       TIMESTAMP    NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_compliance_workflow ON compliance_reports (workflow_id);
CREATE INDEX IF NOT EXISTS idx_compliance_tender   ON compliance_reports (tender_id);

-- ------------------------------------------------------------
-- AUDIT REPORTS (full consolidated report)
-- ------------------------------------------------------------

CREATE TABLE IF NOT EXISTS audit_reports (
    id            VARCHAR(36) PRIMARY KEY DEFAULT uuid_generate_v4()::text,
    workflow_id   VARCHAR(36) NOT NULL REFERENCES workflow_executions(id) ON DELETE CASCADE,
    tender_id     VARCHAR(36) NOT NULL REFERENCES tenders(id) ON DELETE CASCADE,
    legal_output  JSONB,
    proposal_output JSONB,
    audit_output  JSONB,
    final_report  JSONB,
    created_at    TIMESTAMP   NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_audit_workflow ON audit_reports (workflow_id);
CREATE INDEX IF NOT EXISTS idx_audit_tender   ON audit_reports (tender_id);
