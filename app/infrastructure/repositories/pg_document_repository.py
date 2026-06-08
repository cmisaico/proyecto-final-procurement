from typing import List, Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.document import Document, DocumentStatus
from app.domain.repositories.document_repository import DocumentRepository
from app.infrastructure.database.models import DocumentModel


def _to_entity(m: DocumentModel) -> Document:
    return Document(
        id=m.id,
        tender_id=m.tender_id,
        filename=m.filename,
        original_filename=m.original_filename,
        minio_path=m.minio_path,
        file_size=m.file_size,
        mime_type=m.mime_type,
        status=DocumentStatus(m.status) if isinstance(m.status, str) else m.status,
        page_count=m.page_count,
        extracted_text=m.extracted_text,
        created_at=m.created_at,
        updated_at=m.updated_at,
    )


class PgDocumentRepository(DocumentRepository):
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_by_id(self, entity_id: str) -> Optional[Document]:
        result = await self._session.execute(
            select(DocumentModel).where(DocumentModel.id == entity_id)
        )
        m = result.scalar_one_or_none()
        return _to_entity(m) if m else None

    async def get_by_tender_id(self, tender_id: str) -> List[Document]:
        result = await self._session.execute(
            select(DocumentModel).where(DocumentModel.tender_id == tender_id)
        )
        return [_to_entity(m) for m in result.scalars().all()]

    async def save(self, entity: Document) -> Document:
        m = DocumentModel(
            id=entity.id,
            tender_id=entity.tender_id,
            filename=entity.filename,
            original_filename=entity.original_filename,
            minio_path=entity.minio_path,
            file_size=entity.file_size,
            mime_type=entity.mime_type,
            status=entity.status,
            page_count=entity.page_count,
            extracted_text=entity.extracted_text,
        )
        self._session.add(m)
        await self._session.flush()
        return entity

    async def delete(self, entity_id: str) -> None:
        result = await self._session.execute(
            select(DocumentModel).where(DocumentModel.id == entity_id)
        )
        m = result.scalar_one_or_none()
        if m:
            await self._session.delete(m)

    async def update_status(self, document_id: str, status: DocumentStatus) -> None:
        await self._session.execute(
            update(DocumentModel)
            .where(DocumentModel.id == document_id)
            .values(status=status)
        )

    async def update_extracted_text(self, document_id: str, text: str, page_count: int) -> None:
        await self._session.execute(
            update(DocumentModel)
            .where(DocumentModel.id == document_id)
            .values(extracted_text=text, page_count=page_count, status=DocumentStatus.PROCESSED)
        )
