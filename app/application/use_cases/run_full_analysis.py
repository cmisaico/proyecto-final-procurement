import uuid
from dataclasses import dataclass
from typing import Any, Dict, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.supervisor_agent import SupervisorAgent
from app.core.exceptions import TenderNotFoundException
from app.core.logging import get_logger
from app.domain.entities.workflow import (
    AgentRun, AgentStatus, AuditReport, ComplianceReport,
    RiskLevel, WorkflowExecution, WorkflowStatus,
)
from app.infrastructure.repositories.pg_tender_repository import PgTenderRepository
from app.infrastructure.repositories.pg_workflow_repository import PgWorkflowRepository

logger = get_logger(__name__)


@dataclass
class FullAnalysisInput:
    tender_id: str


@dataclass
class FullAnalysisOutput:
    workflow_id: str
    tender_id: str
    correlation_id: str
    status: str
    final_report: Optional[Dict[str, Any]]
    steps_completed: list
    errors: list


class RunFullAnalysisUseCase:
    def __init__(self, session: AsyncSession):
        self._tender_repo   = PgTenderRepository(session)
        self._wf_repo       = PgWorkflowRepository(session)
        self._supervisor    = SupervisorAgent()

    async def execute(self, inp: FullAnalysisInput) -> FullAnalysisOutput:
        tender = await self._tender_repo.get_by_id(inp.tender_id)
        if not tender:
            raise TenderNotFoundException(inp.tender_id)

        wf_id = str(uuid.uuid4())
        wf = WorkflowExecution(
            id=wf_id,
            tender_id=inp.tender_id,
            status=WorkflowStatus.RUNNING,
            input_data={"tender_id": inp.tender_id},
        )
        await self._wf_repo.create_workflow(wf)

        try:
            result = await self._supervisor.execute(
                tender_id=inp.tender_id,
                workflow_id=wf_id,
            )

            await self._wf_repo.update_workflow_status(wf_id, WorkflowStatus.COMPLETED)

            # Persist agent runs
            for agent_name in ["legal", "proposal", "audit"]:
                agent_key = f"{agent_name}_result" if agent_name != "legal" else "legal"
                output = result.get(f"{agent_name}")
                run = AgentRun(
                    workflow_id=wf_id,
                    agent_name=f"{agent_name}_analysis" if agent_name == "legal" else
                               f"{agent_name}_generation" if agent_name == "proposal" else
                               "compliance_audit",
                    status=AgentStatus.COMPLETED,
                    output_data=output,
                )
                await self._wf_repo.create_agent_run(run)

            # Persist compliance report
            final = result.get("final_report") or {}
            risk_raw = final.get("risk_level", "medium")
            try:
                risk = RiskLevel(risk_raw)
            except ValueError:
                risk = RiskLevel.MEDIUM

            compliance = ComplianceReport(
                workflow_id=wf_id,
                tender_id=inp.tender_id,
                compliance_score=final.get("compliance_score", 0.0),
                risk_level=risk,
                issues=final.get("issues", []),
                recommendations=final.get("recommendations", []),
            )
            await self._wf_repo.save_compliance_report(compliance)

            # Persist full audit report
            audit_report = AuditReport(
                workflow_id=wf_id,
                tender_id=inp.tender_id,
                legal_output=result.get("legal"),
                proposal_output=result.get("proposal"),
                audit_output=result.get("audit"),
                final_report=final,
            )
            await self._wf_repo.save_audit_report(audit_report)

            logger.info(
                "Full analysis completed",
                extra={"workflow_id": wf_id, "tender_id": inp.tender_id},
            )

            return FullAnalysisOutput(
                workflow_id=wf_id,
                tender_id=inp.tender_id,
                correlation_id=result["correlation_id"],
                status=WorkflowStatus.COMPLETED.value,
                final_report=final,
                steps_completed=result.get("steps_completed", []),
                errors=result.get("errors", []),
            )

        except Exception as e:
            await self._wf_repo.update_workflow_status(
                wf_id, WorkflowStatus.FAILED, error=str(e)
            )
            logger.error(
                "Full analysis failed",
                extra={"workflow_id": wf_id, "error": str(e)},
            )
            raise
