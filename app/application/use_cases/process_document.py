import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import DocumentNotFoundException
from app.core.logging import get_logger
from app.domain.entities.document import DocumentStatus
from app.domain.entities.chunk import Chunk
from app.infrastructure.database.models import ChunkModel
from app.infrastructure.repositories.pg_document_repository import PgDocumentRepository
from app.infrastructure.storage.factory import storage_client
from app.infrastructure.vector_store.qdrant_client import qdrant_store
from app.services.chunking_service import ChunkingService
from app.services.document_parser_service import DocumentParserService
from app.services.embedding_service import EmbeddingService

logger = get_logger(__name__)


@dataclass
class ProcessDocumentInput:
    document_id: str


@dataclass
class ProcessDocumentOutput:
    document_id: str
    page_count: int
    chunk_count: int
    status: str


class ProcessDocumentUseCase:
    def __init__(self, session: AsyncSession):
        self._repo = PgDocumentRepository(session)
        self._parser = DocumentParserService()
        self._chunker = ChunkingService()
        self._embedder = EmbeddingService()
        self._session = session

    async def execute(self, inp: ProcessDocumentInput) -> ProcessDocumentOutput:
        doc = await self._repo.get_by_id(inp.document_id)
        if not doc:
            raise DocumentNotFoundException(inp.document_id)

        await self._repo.update_status(inp.document_id, DocumentStatus.PROCESSING)

        try:
            content = storage_client.download_file(doc.filename)
            parsed = self._parser.parse_pdf_bytes(content)
            await self._repo.update_extracted_text(inp.document_id, parsed.raw_text, parsed.page_count)

            chunks = self._chunker.chunk_document(inp.document_id, parsed)
            chunk_texts = [c.content for c in chunks]
            embeddings = await self._embedder.embed_texts(chunk_texts)

            chunk_ids = [str(uuid.uuid4()) for _ in chunks]
            payloads = [
                {
                    "chunk_id": cid,
                    "document_id": doc.id,
                    "tender_id": doc.tender_id,
                    "content": c.content,
                    "page_number": c.page_number,
                    "chunk_index": c.chunk_index,
                }
                for cid, c in zip(chunk_ids, chunks)
            ]

            qdrant_store.upsert_chunks(chunk_ids, embeddings, payloads)

            for cid, chunk in zip(chunk_ids, chunks):
                db_chunk = ChunkModel(
                    id=chunk.id,
                    document_id=chunk.document_id,
                    content=chunk.content,
                    chunk_index=chunk.chunk_index,
                    page_number=chunk.page_number,
                    char_start=chunk.char_start,
                    char_end=chunk.char_end,
                    qdrant_id=cid,
                )
                self._session.add(db_chunk)

            logger.info(
                "Document processed",
                extra={"document_id": inp.document_id, "chunks": len(chunks)},
            )
            return ProcessDocumentOutput(
                document_id=inp.document_id,
                page_count=parsed.page_count,
                chunk_count=len(chunks),
                status=DocumentStatus.PROCESSED.value,
            )

        except Exception as e:
            await self._repo.update_status(inp.document_id, DocumentStatus.FAILED)
            logger.error("Document processing failed", extra={"document_id": inp.document_id, "error": str(e)})
            raise
