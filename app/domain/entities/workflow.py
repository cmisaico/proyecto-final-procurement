from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid


class WorkflowStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class AgentStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class WorkflowExecution:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    tender_id: str = ""
    correlation_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    status: WorkflowStatus = WorkflowStatus.PENDING
    input_data: Optional[Dict[str, Any]] = None
    started_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None


@dataclass
class AgentRun:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    workflow_id: str = ""
    agent_name: str = ""
    status: AgentStatus = AgentStatus.PENDING
    input_data: Optional[Dict[str, Any]] = None
    output_data: Optional[Dict[str, Any]] = None
    guardrail_score: Optional[float] = None
    started_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None


@dataclass
class ComplianceReport:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    workflow_id: str = ""
    tender_id: str = ""
    compliance_score: float = 0.0
    risk_level: RiskLevel = RiskLevel.MEDIUM
    issues: List[Dict[str, Any]] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class AuditReport:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    workflow_id: str = ""
    tender_id: str = ""
    legal_output: Optional[Dict[str, Any]] = None
    proposal_output: Optional[Dict[str, Any]] = None
    audit_output: Optional[Dict[str, Any]] = None
    final_report: Optional[Dict[str, Any]] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
