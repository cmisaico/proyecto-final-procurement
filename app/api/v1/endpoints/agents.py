from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.use_cases.analyze_tender import AnalyzeTenderInput, AnalyzeTenderUseCase
from app.core.exceptions import AppException, TenderNotFoundException
from app.infrastructure.database.connection import get_db
from app.infrastructure.repositories.pg_requirement_repository import PgRequirementRepository

router = APIRouter(prefix="/agents", tags=["agents"])


class AnalyzeRequest(BaseModel):
    tender_id: str


class AnalyzeResponse(BaseModel):
    tender_id: str
    analysis: Dict[str, Any]
    requirements_saved: int


class RequirementItem(BaseModel):
    id: str
    type: str
    priority: str
    description: str
    raw_text: Optional[str]


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze_tender(
    body: AnalyzeRequest,
    session: AsyncSession = Depends(get_db),
):
    use_case = AnalyzeTenderUseCase(session)
    try:
        result = await use_case.execute(AnalyzeTenderInput(tender_id=body.tender_id))
    except TenderNotFoundException as e:
        raise HTTPException(status_code=404, detail=e.message)
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    return AnalyzeResponse(**result.__dict__)


@router.get("/requirements/{tender_id}", response_model=List[RequirementItem])
async def get_requirements(
    tender_id: str,
    session: AsyncSession = Depends(get_db),
):
    repo = PgRequirementRepository(session)
    requirements = await repo.get_by_tender_id(tender_id)
    return [
        RequirementItem(
            id=r.id,
            type=r.type.value,
            priority=r.priority.value,
            description=r.description,
            raw_text=r.raw_text,
        )
        for r in requirements
    ]
