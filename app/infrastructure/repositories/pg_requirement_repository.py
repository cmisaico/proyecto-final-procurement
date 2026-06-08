from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.requirement import Requirement, RequirementType, RequirementPriority
from app.domain.repositories.requirement_repository import RequirementRepository
from app.infrastructure.database.models import RequirementModel


def _to_entity(m: RequirementModel) -> Requirement:
    return Requirement(
        id=m.id,
        tender_id=m.tender_id,
        document_id=m.document_id,
        type=RequirementType(m.type) if isinstance(m.type, str) else m.type,
        priority=RequirementPriority(m.priority) if isinstance(m.priority, str) else m.priority,
        description=m.description,
        raw_text=m.raw_text,
        deadline=m.deadline,
        created_at=m.created_at,
    )


class PgRequirementRepository(RequirementRepository):
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_by_id(self, entity_id: str) -> Optional[Requirement]:
        result = await self._session.execute(
            select(RequirementModel).where(RequirementModel.id == entity_id)
        )
        m = result.scalar_one_or_none()
        return _to_entity(m) if m else None

    async def get_by_tender_id(self, tender_id: str) -> List[Requirement]:
        result = await self._session.execute(
            select(RequirementModel).where(RequirementModel.tender_id == tender_id)
        )
        return [_to_entity(m) for m in result.scalars().all()]

    async def save(self, entity: Requirement) -> Requirement:
        m = RequirementModel(
            id=entity.id,
            tender_id=entity.tender_id,
            document_id=entity.document_id,
            type=entity.type,
            priority=entity.priority,
            description=entity.description,
            raw_text=entity.raw_text,
            deadline=entity.deadline,
        )
        self._session.add(m)
        await self._session.flush()
        return entity

    async def save_bulk(self, requirements: List[Requirement]) -> List[Requirement]:
        for r in requirements:
            await self.save(r)
        return requirements

    async def delete(self, entity_id: str) -> None:
        result = await self._session.execute(
            select(RequirementModel).where(RequirementModel.id == entity_id)
        )
        m = result.scalar_one_or_none()
        if m:
            await self._session.delete(m)
