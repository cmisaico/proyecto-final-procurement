from abc import abstractmethod
from typing import List

from app.domain.entities.requirement import Requirement
from app.domain.repositories.base import BaseRepository


class RequirementRepository(BaseRepository[Requirement]):
    @abstractmethod
    async def get_by_tender_id(self, tender_id: str) -> List[Requirement]:
        ...

    @abstractmethod
    async def save_bulk(self, requirements: List[Requirement]) -> List[Requirement]:
        ...
