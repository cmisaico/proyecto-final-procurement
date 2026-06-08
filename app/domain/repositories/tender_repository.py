from abc import abstractmethod
from typing import List, Optional

from app.domain.entities.tender import Tender
from app.domain.repositories.base import BaseRepository


class TenderRepository(BaseRepository[Tender]):
    @abstractmethod
    async def get_by_project_id(self, project_id: str) -> List[Tender]:
        ...
