import json
from datetime import datetime
from typing import List, Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.workflow import (
    AgentRun, AgentStatus, AuditReport, ComplianceReport,
    RiskLevel, WorkflowExecution, WorkflowStatus,
)
from app.infrastructure.database.models_fase02 import (
    AgentResultModel, AgentRunModel, AuditReportModel,
    ComplianceReportModel, WorkflowExecutionModel,
)


def _wf_to_entity(m: WorkflowExecutionModel) -> WorkflowExecution:
    return WorkflowExecution(
        id=m.id, tender_id=m.tender_id, correlation_id=m.correlation_id,
        status=WorkflowStatus(m.status) if isinstance(m.status, str) else m.status,
        input_data=m.input_data, started_at=m.started_at,
        completed_at=m.completed_at, error_message=m.error_message,
    )


def _run_to_entity(m: AgentRunModel) -> AgentRun:
    return AgentRun(
        id=m.id, workflow_id=m.workflow_id, agent_name=m.agent_name,
        status=AgentStatus(m.status) if isinstance(m.status, str) else m.status,
        input_data=m.input_data, output_data=m.output_data,
        guardrail_score=m.guardrail_score, started_at=m.started_at,
        completed_at=m.completed_at, error_message=m.error_message,
    )


class PgWorkflowRepository:
    def __init__(self, session: AsyncSession):
        self._s = session

    # ── WorkflowExecution ─────────────────────

    async def create_workflow(self, wf: WorkflowExecution) -> WorkflowExecution:
        m = WorkflowExecutionModel(
            id=wf.id, tender_id=wf.tender_id, correlation_id=wf.correlation_id,
            status=wf.status.value, input_data=wf.input_data,
            started_at=wf.started_at,
        )
        self._s.add(m)
        await self._s.flush()
        return wf

    async def get_workflow(self, workflow_id: str) -> Optional[WorkflowExecution]:
        result = await self._s.execute(
            select(WorkflowExecutionModel).where(WorkflowExecutionModel.id == workflow_id)
        )
        m = result.scalar_one_or_none()
        return _wf_to_entity(m) if m else None

    async def update_workflow_status(
        self, workflow_id: str, status: WorkflowStatus, error: Optional[str] = None
    ) -> None:
        vals = {"status": status.value}
        if status in (WorkflowStatus.COMPLETED, WorkflowStatus.FAILED):
            vals["completed_at"] = datetime.utcnow()
        if error:
            vals["error_message"] = error
        await self._s.execute(
            update(WorkflowExecutionModel)
            .where(WorkflowExecutionModel.id == workflow_id)
            .values(**vals)
        )

    # ── AgentRun ──────────────────────────────

    async def create_agent_run(self, run: AgentRun) -> AgentRun:
        m = AgentRunModel(
            id=run.id, workflow_id=run.workflow_id, agent_name=run.agent_name,
            status=run.status.value, input_data=run.input_data,
        )
        self._s.add(m)
        await self._s.flush()
        return run

    async def complete_agent_run(
        self, run_id: str, output: dict, guardrail_score: float, status: AgentStatus
    ) -> None:
        await self._s.execute(
            update(AgentRunModel)
            .where(AgentRunModel.id == run_id)
            .values(
                status=status.value,
                output_data=output,
                guardrail_score=guardrail_score,
                completed_at=datetime.utcnow(),
            )
        )

    async def get_agent_runs_by_workflow(self, workflow_id: str) -> List[AgentRun]:
        result = await self._s.execute(
            select(AgentRunModel).where(AgentRunModel.workflow_id == workflow_id)
        )
        return [_run_to_entity(m) for m in result.scalars().all()]

    # ── ComplianceReport ──────────────────────

    async def save_compliance_report(self, report: ComplianceReport) -> ComplianceReport:
        m = ComplianceReportModel(
            id=report.id, workflow_id=report.workflow_id, tender_id=report.tender_id,
            compliance_score=report.compliance_score,
            risk_level=report.risk_level.value,
            issues=report.issues,
            recommendations=report.recommendations,
        )
        self._s.add(m)
        await self._s.flush()
        return report

    async def get_compliance_report(self, workflow_id: str) -> Optional[ComplianceReport]:
        result = await self._s.execute(
            select(ComplianceReportModel).where(ComplianceReportModel.workflow_id == workflow_id)
        )
        m = result.scalar_one_or_none()
        if not m:
            return None
        return ComplianceReport(
            id=m.id, workflow_id=m.workflow_id, tender_id=m.tender_id,
            compliance_score=m.compliance_score,
            risk_level=RiskLevel(m.risk_level) if isinstance(m.risk_level, str) else m.risk_level,
            issues=m.issues or [],
            recommendations=m.recommendations or [],
            created_at=m.created_at,
        )

    async def get_compliance_by_tender(self, tender_id: str) -> Optional[ComplianceReport]:
        result = await self._s.execute(
            select(ComplianceReportModel)
            .where(ComplianceReportModel.tender_id == tender_id)
            .order_by(ComplianceReportModel.created_at.desc())
            .limit(1)
        )
        m = result.scalar_one_or_none()
        if not m:
            return None
        return ComplianceReport(
            id=m.id, workflow_id=m.workflow_id, tender_id=m.tender_id,
            compliance_score=m.compliance_score,
            risk_level=RiskLevel(m.risk_level) if isinstance(m.risk_level, str) else m.risk_level,
            issues=m.issues or [],
            recommendations=m.recommendations or [],
            created_at=m.created_at,
        )

    # ── AuditReport ───────────────────────────

    async def save_audit_report(self, report: AuditReport) -> AuditReport:
        m = AuditReportModel(
            id=report.id, workflow_id=report.workflow_id, tender_id=report.tender_id,
            legal_output=report.legal_output,
            proposal_output=report.proposal_output,
            audit_output=report.audit_output,
            final_report=report.final_report,
        )
        self._s.add(m)
        await self._s.flush()
        return report

    async def get_audit_report(self, workflow_id: str) -> Optional[AuditReport]:
        result = await self._s.execute(
            select(AuditReportModel).where(AuditReportModel.workflow_id == workflow_id)
        )
        m = result.scalar_one_or_none()
        if not m:
            return None
        return AuditReport(
            id=m.id, workflow_id=m.workflow_id, tender_id=m.tender_id,
            legal_output=m.legal_output, proposal_output=m.proposal_output,
            audit_output=m.audit_output, final_report=m.final_report,
            created_at=m.created_at,
        )
