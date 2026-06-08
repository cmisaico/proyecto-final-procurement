import io
import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.domain.entities.document import Document
from app.domain.entities.tender import Tender, TenderStatus
from app.infrastructure.database.models import ProjectModel, TenderModel, UserModel
from app.infrastructure.repositories.pg_document_repository import PgDocumentRepository
from app.infrastructure.repositories.pg_tender_repository import PgTenderRepository
from app.infrastructure.storage.factory import storage_client

logger = get_logger(__name__)

_SYSTEM_USER_ID = "00000000-0000-0000-0000-000000000001"
_SYSTEM_PROJECT_ID = "00000000-0000-0000-0000-000000000002"


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
        self._tender_repo = PgTenderRepository(session)
        self._session = session

    async def _ensure_system_ancestors(self) -> None:
        """Garantiza que el user y project del sistema existen (FK chain)."""
        user = await self._session.get(UserModel, _SYSTEM_USER_ID)
        if not user:
            self._session.add(UserModel(
                id=_SYSTEM_USER_ID,
                email="system@procurement.local",
                full_name="System",
                is_active=True,
                created_at=datetime.utcnow(),
            ))
            await self._session.flush()

        project = await self._session.get(ProjectModel, _SYSTEM_PROJECT_ID)
        if not project:
            self._session.add(ProjectModel(
                id=_SYSTEM_PROJECT_ID,
                user_id=_SYSTEM_USER_ID,
                name="Default Project",
                created_at=datetime.utcnow(),
            ))
            await self._session.flush()

    async def execute(self, inp: UploadDocumentInput) -> UploadDocumentOutput:
        await self._ensure_system_ancestors()

        existing = await self._tender_repo.get_by_id(inp.tender_id)
        if not existing:
            await self._tender_repo.save(Tender(
                id=inp.tender_id,
                project_id=_SYSTEM_PROJECT_ID,
                title=inp.tender_id,
                status=TenderStatus.ACTIVE,
            ))
            logger.info("Tender auto-created", extra={"tender_id": inp.tender_id})

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
