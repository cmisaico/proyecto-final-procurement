from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.connection import get_db
from app.infrastructure.repositories.pg_workflow_repository import PgWorkflowRepository

router = APIRouter(tags=["reports & compliance"])


class ComplianceReportResponse(BaseModel):
    id: str
    workflow_id: str
    tender_id: str
    compliance_score: float
    risk_level: str
    issues: List[Dict[str, Any]]
    recommendations: List[str]
    created_at: str


class AuditReportResponse(BaseModel):
    id: str
    workflow_id: str
    tender_id: str
    legal_output: Optional[Dict[str, Any]]
    proposal_output: Optional[Dict[str, Any]]
    audit_output: Optional[Dict[str, Any]]
    final_report: Optional[Dict[str, Any]]
    created_at: str


class DashboardResponse(BaseModel):
    tender_id: str
    workflow_id: Optional[str]
    compliance_score: Optional[float]
    risk_level: Optional[str]
    requirements_count: int
    checklist_items: int
    issues_count: int
    recommendations: List[str]
    key_dates: List[Dict[str, Any]]


@router.get("/reports/{workflow_id}", response_model=AuditReportResponse)
async def get_report(
    workflow_id: str,
    session: AsyncSession = Depends(get_db),
):
    """Get full audit report for a workflow execution."""
    repo = PgWorkflowRepository(session)
    report = await repo.get_audit_report(workflow_id)
    if not report:
        raise HTTPException(status_code=404, detail=f"Report for workflow {workflow_id} not found")
    return AuditReportResponse(
        id=report.id,
        workflow_id=report.workflow_id,
        tender_id=report.tender_id,
        legal_output=report.legal_output,
        proposal_output=report.proposal_output,
        audit_output=report.audit_output,
        final_report=report.final_report,
        created_at=report.created_at.isoformat(),
    )


@router.get("/compliance/{tender_id}", response_model=ComplianceReportResponse)
async def get_compliance(
    tender_id: str,
    session: AsyncSession = Depends(get_db),
):
    """Get the latest compliance report for a tender."""
    repo = PgWorkflowRepository(session)
    report = await repo.get_compliance_by_tender(tender_id)
    if not report:
        raise HTTPException(status_code=404, detail=f"No compliance report found for tender {tender_id}")
    return ComplianceReportResponse(
        id=report.id,
        workflow_id=report.workflow_id,
        tender_id=report.tender_id,
        compliance_score=report.compliance_score,
        risk_level=report.risk_level.value,
        issues=report.issues,
        recommendations=report.recommendations,
        created_at=report.created_at.isoformat(),
    )


@router.get("/dashboard/{tender_id}", response_model=DashboardResponse)
async def get_dashboard(
    tender_id: str,
    session: AsyncSession = Depends(get_db),
):
    """Dashboard summary for frontend: score, checklist, risks, dates."""
    repo = PgWorkflowRepository(session)
    compliance = await repo.get_compliance_by_tender(tender_id)

    if not compliance:
        return DashboardResponse(
            tender_id=tender_id,
            workflow_id=None,
            compliance_score=None,
            risk_level=None,
            requirements_count=0,
            checklist_items=0,
            issues_count=0,
            recommendations=[],
            key_dates=[],
        )

    audit_report = await repo.get_audit_report(compliance.workflow_id)
    final = (audit_report.final_report or {}) if audit_report else {}

    return DashboardResponse(
        tender_id=tender_id,
        workflow_id=compliance.workflow_id,
        compliance_score=compliance.compliance_score,
        risk_level=compliance.risk_level.value,
        requirements_count=final.get("requirements_count", 0),
        checklist_items=len(final.get("checklist", [])),
        issues_count=len(compliance.issues),
        recommendations=compliance.recommendations[:5],
        key_dates=final.get("deadlines", []),
    )
