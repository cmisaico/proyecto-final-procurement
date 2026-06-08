from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.compliance_audit_agent import ComplianceAuditAgent
from app.agents.legal_analysis_agent import LegalAnalysisAgent
from app.agents.proposal_generation_agent import ProposalGenerationAgent
from app.application.use_cases.run_full_analysis import FullAnalysisInput, RunFullAnalysisUseCase
from app.core.exceptions import AppException, TenderNotFoundException
from app.infrastructure.database.connection import get_db
from app.infrastructure.repositories.pg_workflow_repository import PgWorkflowRepository

router = APIRouter(tags=["workflow & agents"])


# ── Request/Response models ───────────────────────────────────────────

class FullAnalysisRequest(BaseModel):
    tender_id: str


class FullAnalysisResponse(BaseModel):
    workflow_id: str
    tender_id: str
    correlation_id: str
    status: str
    steps_completed: List[str]
    errors: List[str]
    final_report: Optional[Dict[str, Any]]


class LegalAgentRequest(BaseModel):
    tender_id: str
    correlation_id: Optional[str] = None


class LegalAgentResponse(BaseModel):
    tender_id: str
    output: Dict[str, Any]
    guardrail: Dict[str, Any]
    context_chunks: int


class ProposalAgentRequest(BaseModel):
    tender_id: str
    legal_output: Dict[str, Any]
    correlation_id: Optional[str] = None


class ProposalAgentResponse(BaseModel):
    tender_id: str
    output: Dict[str, Any]
    guardrail: Dict[str, Any]
    context_chunks: int


class AuditAgentRequest(BaseModel):
    tender_id: str
    legal_output: Dict[str, Any]
    proposal_output: Dict[str, Any]
    correlation_id: Optional[str] = None


class AuditAgentResponse(BaseModel):
    tender_id: str
    output: Dict[str, Any]
    guardrail: Dict[str, Any]
    context_chunks: int


class WorkflowStatusResponse(BaseModel):
    workflow_id: str
    tender_id: str
    correlation_id: str
    status: str
    started_at: str
    completed_at: Optional[str]
    error_message: Optional[str]


# ── Endpoints ─────────────────────────────────────────────────────────

@router.post("/workflow/full-analysis", response_model=FullAnalysisResponse)
async def run_full_analysis(
    body: FullAnalysisRequest,
    session: AsyncSession = Depends(get_db),
):
    """Run the complete multi-agent workflow: Legal → Proposal → Audit → Report."""
    use_case = RunFullAnalysisUseCase(session)
    try:
        result = await use_case.execute(FullAnalysisInput(tender_id=body.tender_id))
    except TenderNotFoundException as e:
        raise HTTPException(status_code=404, detail=e.message)
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)

    return FullAnalysisResponse(
        workflow_id=result.workflow_id,
        tender_id=result.tender_id,
        correlation_id=result.correlation_id,
        status=result.status,
        steps_completed=result.steps_completed,
        errors=result.errors,
        final_report=result.final_report,
    )


@router.post("/agents/legal", response_model=LegalAgentResponse)
async def run_legal_agent(body: LegalAgentRequest):
    """Run only the Legal Analysis Agent."""
    import uuid
    agent = LegalAnalysisAgent()
    try:
        result = await agent.run(
            tender_id=body.tender_id,
            correlation_id=body.correlation_id or str(uuid.uuid4()),
        )
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    return LegalAgentResponse(tender_id=body.tender_id, **result)


@router.post("/agents/proposal", response_model=ProposalAgentResponse)
async def run_proposal_agent(body: ProposalAgentRequest):
    """Run only the Proposal Generation Agent."""
    import uuid
    agent = ProposalGenerationAgent()
    try:
        result = await agent.run(
            tender_id=body.tender_id,
            legal_output=body.legal_output,
            correlation_id=body.correlation_id or str(uuid.uuid4()),
        )
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    return ProposalAgentResponse(tender_id=body.tender_id, **result)


@router.post("/agents/audit", response_model=AuditAgentResponse)
async def run_audit_agent(body: AuditAgentRequest):
    """Run only the Compliance Audit Agent."""
    import uuid
    agent = ComplianceAuditAgent()
    try:
        result = await agent.run(
            tender_id=body.tender_id,
            legal_output=body.legal_output,
            proposal_output=body.proposal_output,
            correlation_id=body.correlation_id or str(uuid.uuid4()),
        )
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    return AuditAgentResponse(tender_id=body.tender_id, **result)


@router.get("/workflow/{workflow_id}", response_model=WorkflowStatusResponse)
async def get_workflow(
    workflow_id: str,
    session: AsyncSession = Depends(get_db),
):
    repo = PgWorkflowRepository(session)
    wf = await repo.get_workflow(workflow_id)
    if not wf:
        raise HTTPException(status_code=404, detail=f"Workflow {workflow_id} not found")
    return WorkflowStatusResponse(
        workflow_id=wf.id,
        tender_id=wf.tender_id,
        correlation_id=wf.correlation_id,
        status=wf.status.value,
        started_at=wf.started_at.isoformat(),
        completed_at=wf.completed_at.isoformat() if wf.completed_at else None,
        error_message=wf.error_message,
    )
