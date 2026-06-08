from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
import uuid


@dataclass
class Chunk:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    document_id: str = ""
    content: str = ""
    chunk_index: int = 0
    page_number: Optional[int] = None
    char_start: int = 0
    char_end: int = 0
    qdrant_id: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
