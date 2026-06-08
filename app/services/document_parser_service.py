import io
import re
from dataclasses import dataclass
from typing import List, Optional

import pdfplumber

from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class ParsedPage:
    page_number: int
    text: str
    char_start: int
    char_end: int


@dataclass
class ParsedDocument:
    raw_text: str
    pages: List[ParsedPage]
    page_count: int


class DocumentParserService:
    def parse_pdf_bytes(self, content: bytes) -> ParsedDocument:
        pages: List[ParsedPage] = []
        full_text_parts: List[str] = []
        offset = 0

        with pdfplumber.open(io.BytesIO(content)) as pdf:
            for i, page in enumerate(pdf.pages, start=1):
                text = page.extract_text() or ""
                text = self._normalize(text)
                char_start = offset
                char_end = offset + len(text)
                pages.append(ParsedPage(
                    page_number=i,
                    text=text,
                    char_start=char_start,
                    char_end=char_end,
                ))
                full_text_parts.append(text)
                offset = char_end + 1  # +1 for newline separator

        raw_text = "\n".join(full_text_parts)
        logger.info("PDF parsed", extra={"pages": len(pages), "chars": len(raw_text)})
        return ParsedDocument(raw_text=raw_text, pages=pages, page_count=len(pages))

    def _normalize(self, text: str) -> str:
        # Collapse multiple whitespace/newlines
        text = re.sub(r"\r\n|\r", "\n", text)
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()
