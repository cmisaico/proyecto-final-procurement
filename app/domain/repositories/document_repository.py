from abc import abstractmethod
from typing import List, Optional

from app.domain.entities.document import Document, DocumentStatus
from app.domain.repositories.base import BaseRepository


class DocumentRepository(BaseRepository[Document]):
    @abstractmethod
    async def get_by_tender_id(self, tender_id: str) -> List[Document]:
        ...

    @abstractmethod
    async def update_status(self, document_id: str, status: DocumentStatus) -> None:
        ...

    @abstractmethod
    async def update_extracted_text(
        self, document_id: str, text: str, page_count: int
    ) -> None:
        ...
