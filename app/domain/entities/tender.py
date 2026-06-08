from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional
import uuid


class TenderStatus(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    ANALYZED = "analyzed"
    CLOSED = "closed"


@dataclass
class Tender:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    project_id: str = ""
    title: str = ""
    description: Optional[str] = None
    status: TenderStatus = TenderStatus.DRAFT
    deadline: Optional[datetime] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
