from dataclasses import dataclass
from typing import Any, Dict, List

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.procurement_agent import ProcurementAnalysisAgent
from app.core.exceptions import TenderNotFoundException
from app.core.logging import get_logger
from app.domain.entities.requirement import Requirement, RequirementPriority, RequirementType
from app.infrastructure.repositories.pg_document_repository import PgDocumentRepository
from app.infrastructure.repositories.pg_requirement_repository import PgRequirementRepository
from app.infrastructure.repositories.pg_tender_repository import PgTenderRepository

logger = get_logger(__name__)


@dataclass
class AnalyzeTenderInput:
    tender_id: str


@dataclass
class AnalyzeTenderOutput:
    tender_id: str
    analysis: Dict[str, Any]
    requirements_saved: int


class AnalyzeTenderUseCase:
    def __init__(self, session: AsyncSession):
        self._tender_repo = PgTenderRepository(session)
        self._doc_repo = PgDocumentRepository(session)
        self._req_repo = PgRequirementRepository(session)
        self._agent = ProcurementAnalysisAgent()

    async def execute(self, inp: AnalyzeTenderInput) -> AnalyzeTenderOutput:
        tender = await self._tender_repo.get_by_id(inp.tender_id)
        if not tender:
            raise TenderNotFoundException(inp.tender_id)

        docs = await self._doc_repo.get_by_tender_id(inp.tender_id)
        document_id = docs[0].id if docs else ""

        result = await self._agent.analyze(tender_id=inp.tender_id, document_id=document_id)
        analysis = result.get("analysis", {})

        requirements: List[Requirement] = []
        for req_data in analysis.get("requirements", []):
            req_type = self._map_type(req_data.get("type", "other"))
            req_priority = (
                RequirementPriority.MANDATORY
                if req_data.get("priority") == "mandatory"
                else RequirementPriority.OPTIONAL
            )
            requirements.append(Requirement(
                tender_id=inp.tender_id,
                document_id=document_id,
                type=req_type,
                priority=req_priority,
                description=req_data.get("description", ""),
                raw_text=req_data.get("raw_text"),
            ))

        if requirements:
            await self._req_repo.save_bulk(requirements)

        logger.info(
            "Tender analyzed",
            extra={"tender_id": inp.tender_id, "requirements": len(requirements)},
        )
        return AnalyzeTenderOutput(
            tender_id=inp.tender_id,
            analysis=analysis,
            requirements_saved=len(requirements),
        )

    def _map_type(self, raw: str) -> RequirementType:
        mapping = {
            "document": RequirementType.DOCUMENT,
            "technical": RequirementType.TECHNICAL,
            "financial": RequirementType.FINANCIAL,
            "legal": RequirementType.LEGAL,
            "deadline": RequirementType.DEADLINE,
            "restriction": RequirementType.RESTRICTION,
        }
        return mapping.get(raw, RequirementType.OTHER)
