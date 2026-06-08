from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional
import uuid


class DocumentStatus(str, Enum):
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    PROCESSED = "processed"
    FAILED = "failed"


@dataclass
class Document:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    tender_id: str = ""
    filename: str = ""
    original_filename: str = ""
    minio_path: str = ""
    file_size: int = 0
    mime_type: str = "application/pdf"
    status: DocumentStatus = DocumentStatus.UPLOADED
    page_count: int = 0
    extracted_text: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
