from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional
import uuid


class RequirementType(str, Enum):
    DOCUMENT = "document"
    TECHNICAL = "technical"
    FINANCIAL = "financial"
    LEGAL = "legal"
    DEADLINE = "deadline"
    RESTRICTION = "restriction"
    OTHER = "other"


class RequirementPriority(str, Enum):
    MANDATORY = "mandatory"
    OPTIONAL = "optional"


@dataclass
class Requirement:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    tender_id: str = ""
    document_id: str = ""
    type: RequirementType = RequirementType.OTHER
    priority: RequirementPriority = RequirementPriority.MANDATORY
    description: str = ""
    raw_text: Optional[str] = None
    deadline: Optional[datetime] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
