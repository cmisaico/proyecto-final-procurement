from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.tender import Tender, TenderStatus
from app.domain.repositories.tender_repository import TenderRepository
from app.infrastructure.database.models import TenderModel


def _to_entity(m: TenderModel) -> Tender:
    return Tender(
        id=m.id,
        project_id=m.project_id,
        title=m.title,
        description=m.description,
        status=TenderStatus(m.status) if isinstance(m.status, str) else m.status,
        deadline=m.deadline,
        created_at=m.created_at,
        updated_at=m.updated_at,
    )


class PgTenderRepository(TenderRepository):
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_by_id(self, entity_id: str) -> Optional[Tender]:
        result = await self._session.execute(
            select(TenderModel).where(TenderModel.id == entity_id)
        )
        m = result.scalar_one_or_none()
        return _to_entity(m) if m else None

    async def get_by_project_id(self, project_id: str) -> List[Tender]:
        result = await self._session.execute(
            select(TenderModel).where(TenderModel.project_id == project_id)
        )
        return [_to_entity(m) for m in result.scalars().all()]

    async def save(self, entity: Tender) -> Tender:
        m = TenderModel(
            id=entity.id,
            project_id=entity.project_id,
            title=entity.title,
            description=entity.description,
            status=entity.status,
            deadline=entity.deadline,
        )
        self._session.add(m)
        await self._session.flush()
        return entity

    async def delete(self, entity_id: str) -> None:
        result = await self._session.execute(
            select(TenderModel).where(TenderModel.id == entity_id)
        )
        m = result.scalar_one_or_none()
        if m:
            await self._session.delete(m)
