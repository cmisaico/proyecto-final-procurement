from typing import List

from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.core.config import settings
from app.core.logging import get_logger
from app.domain.entities.chunk import Chunk
from app.services.document_parser_service import ParsedDocument

logger = get_logger(__name__)


class ChunkingService:
    def __init__(self):
        self._splitter = RecursiveCharacterTextSplitter(
            chunk_size=settings.CHUNK_SIZE,
            chunk_overlap=settings.CHUNK_OVERLAP,
            separators=["\n\n", "\n", ". ", " ", ""],
            length_function=len,
        )

    def chunk_document(self, document_id: str, parsed: ParsedDocument) -> List[Chunk]:
        texts = self._splitter.split_text(parsed.raw_text)
        chunks: List[Chunk] = []

        offset = 0
        for i, text in enumerate(texts):
            char_start = parsed.raw_text.find(text, offset)
            if char_start == -1:
                char_start = offset
            char_end = char_start + len(text)
            offset = max(offset, char_end - settings.CHUNK_OVERLAP)

            page_number = self._find_page(char_start, parsed)

            chunks.append(Chunk(
                document_id=document_id,
                content=text,
                chunk_index=i,
                page_number=page_number,
                char_start=char_start,
                char_end=char_end,
            ))

        logger.info("Document chunked", extra={"document_id": document_id, "chunks": len(chunks)})
        return chunks

    def _find_page(self, char_start: int, parsed: ParsedDocument) -> int:
        for page in parsed.pages:
            if page.char_start <= char_start <= page.char_end:
                return page.page_number
        return 1
