import io
import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.domain.entities.document import Document
from app.infrastructure.repositories.pg_document_repository import PgDocumentRepository
from app.infrastructure.storage.factory import storage_client

logger = get_logger(__name__)


@dataclass
class UploadDocumentInput:
    tender_id: str
    filename: str
    content: bytes
    content_type: str = "application/pdf"


@dataclass
class UploadDocumentOutput:
    document_id: str
    tender_id: str
    filename: str
    minio_path: str
    file_size: int


class UploadDocumentUseCase:
    def __init__(self, session: AsyncSession):
        self._repo = PgDocumentRepository(session)

    async def execute(self, inp: UploadDocumentInput) -> UploadDocumentOutput:
        doc_id = str(uuid.uuid4())
        safe_name = f"{doc_id}/{inp.filename}"
        minio_path = storage_client.upload_file(
            object_name=safe_name,
            data=io.BytesIO(inp.content),
            size=len(inp.content),
            content_type=inp.content_type,
        )

        doc = Document(
            id=doc_id,
            tender_id=inp.tender_id,
            filename=safe_name,
            original_filename=inp.filename,
            minio_path=minio_path,
            file_size=len(inp.content),
            mime_type=inp.content_type,
        )
        await self._repo.save(doc)
        logger.info("Document uploaded", extra={"document_id": doc_id, "tender_id": inp.tender_id})

        return UploadDocumentOutput(
            document_id=doc_id,
            tender_id=inp.tender_id,
            filename=inp.filename,
            minio_path=minio_path,
            file_size=len(inp.content),
        )
