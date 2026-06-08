from datetime import datetime
from sqlalchemy import Column, DateTime, Enum, Float, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB

from app.infrastructure.database.connection import Base
from app.domain.entities.workflow import WorkflowStatus, AgentStatus, RiskLevel

_vals = lambda e: [m.value for m in e]

pg_workflow_status = Enum(*_vals(WorkflowStatus), name="workflow_status", create_type=False)
pg_agent_status    = Enum(*_vals(AgentStatus),    name="agent_status",    create_type=False)
pg_risk_level      = Enum(*_vals(RiskLevel),       name="risk_level",      create_type=False)


class WorkflowExecutionModel(Base):
    __tablename__ = "workflow_executions"

    id             = Column(String(36), primary_key=True)
    tender_id      = Column(String(36), ForeignKey("tenders.id"), nullable=False, index=True)
    correlation_id = Column(String(36), nullable=False, unique=True, index=True)
    status         = Column(pg_workflow_status, nullable=False, default=WorkflowStatus.PENDING.value)
    input_data     = Column(JSONB)
    started_at     = Column(DateTime, nullable=False, default=datetime.utcnow)
    completed_at   = Column(DateTime)
    error_message  = Column(Text)


class AgentRunModel(Base):
    __tablename__ = "agent_runs"

    id              = Column(String(36), primary_key=True)
    workflow_id     = Column(String(36), ForeignKey("workflow_executions.id"), nullable=False, index=True)
    agent_name      = Column(String(100), nullable=False, index=True)
    status          = Column(pg_agent_status, nullable=False, default=AgentStatus.PENDING.value)
    input_data      = Column(JSONB)
    output_data     = Column(JSONB)
    guardrail_score = Column(Float)
    started_at      = Column(DateTime, nullable=False, default=datetime.utcnow)
    completed_at    = Column(DateTime)
    error_message   = Column(Text)


class AgentResultModel(Base):
    __tablename__ = "agent_results"

    id           = Column(String(36), primary_key=True)
    agent_run_id = Column(String(36), ForeignKey("agent_runs.id"), nullable=False, index=True)
    result_type  = Column(String(100), nullable=False)
    data         = Column(JSONB, nullable=False)
    created_at   = Column(DateTime, nullable=False, default=datetime.utcnow)


class ComplianceReportModel(Base):
    __tablename__ = "compliance_reports"

    id               = Column(String(36), primary_key=True)
    workflow_id      = Column(String(36), ForeignKey("workflow_executions.id"), nullable=False, index=True)
    tender_id        = Column(String(36), ForeignKey("tenders.id"), nullable=False, index=True)
    compliance_score = Column(Float, nullable=False, default=0.0)
    risk_level       = Column(pg_risk_level, nullable=False, default=RiskLevel.MEDIUM.value)
    issues           = Column(JSONB, nullable=False, default=list)
    recommendations  = Column(JSONB, nullable=False, default=list)
    created_at       = Column(DateTime, nullable=False, default=datetime.utcnow)


class AuditReportModel(Base):
    __tablename__ = "audit_reports"

    id               = Column(String(36), primary_key=True)
    workflow_id      = Column(String(36), ForeignKey("workflow_executions.id"), nullable=False, index=True)
    tender_id        = Column(String(36), ForeignKey("tenders.id"), nullable=False, index=True)
    legal_output     = Column(JSONB)
    proposal_output  = Column(JSONB)
    audit_output     = Column(JSONB)
    final_report     = Column(JSONB)
    created_at       = Column(DateTime, nullable=False, default=datetime.utcnow)
