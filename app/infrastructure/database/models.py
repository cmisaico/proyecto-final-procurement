from datetime import datetime
from sqlalchemy import Boolean, Column, DateTime, Enum, ForeignKey, Integer, String, Text, BigInteger
from sqlalchemy.orm import relationship

from app.infrastructure.database.connection import Base
from app.domain.entities.document import DocumentStatus
from app.domain.entities.tender import TenderStatus
from app.domain.entities.requirement import RequirementType, RequirementPriority

# Pre-declared PG enum types that match init_db.sql (create_type=False = already exist)
_vals = lambda e: [m.value for m in e]

pg_doc_status   = Enum(*_vals(DocumentStatus),       name="document_status",       create_type=False)
pg_tender_status = Enum(*_vals(TenderStatus),          name="tender_status",         create_type=False)
pg_req_type     = Enum(*_vals(RequirementType),       name="requirement_type",      create_type=False)
pg_req_priority = Enum(*_vals(RequirementPriority),   name="requirement_priority",  create_type=False)


class UserModel(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    full_name = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    projects = relationship("ProjectModel", back_populates="user")


class ProjectModel(Base):
    __tablename__ = "projects"

    id = Column(String(36), primary_key=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    user = relationship("UserModel", back_populates="projects")
    tenders = relationship("TenderModel", back_populates="project")


class TenderModel(Base):
    __tablename__ = "tenders"

    id = Column(String(36), primary_key=True)
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=False, index=True)
    title = Column(String(500), nullable=False)
    description = Column(Text)
    status = Column(pg_tender_status, default=TenderStatus.DRAFT.value, nullable=False)
    deadline = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    project = relationship("ProjectModel", back_populates="tenders")
    documents = relationship("DocumentModel", back_populates="tender")
    requirements = relationship("RequirementModel", back_populates="tender")


class DocumentModel(Base):
    __tablename__ = "documents"

    id = Column(String(36), primary_key=True)
    tender_id = Column(String(36), ForeignKey("tenders.id"), nullable=False, index=True)
    filename = Column(String(500), nullable=False)
    original_filename = Column(String(500), nullable=False)
    minio_path = Column(String(1000), nullable=False)
    file_size = Column(BigInteger, default=0)
    mime_type = Column(String(100), default="application/pdf")
    status = Column(pg_doc_status, default=DocumentStatus.UPLOADED.value, nullable=False)
    page_count = Column(Integer, default=0)
    extracted_text = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    tender = relationship("TenderModel", back_populates="documents")
    chunks = relationship("ChunkModel", back_populates="document")


class ChunkModel(Base):
    __tablename__ = "chunks"

    id = Column(String(36), primary_key=True)
    document_id = Column(String(36), ForeignKey("documents.id"), nullable=False, index=True)
    content = Column(Text, nullable=False)
    chunk_index = Column(Integer, nullable=False)
    page_number = Column(Integer)
    char_start = Column(Integer, default=0)
    char_end = Column(Integer, default=0)
    qdrant_id = Column(String(36), index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    document = relationship("DocumentModel", back_populates="chunks")


class RequirementModel(Base):
    __tablename__ = "requirements"

    id = Column(String(36), primary_key=True)
    tender_id = Column(String(36), ForeignKey("tenders.id"), nullable=False, index=True)
    document_id = Column(String(36), ForeignKey("documents.id"), nullable=False)
    type = Column(pg_req_type, nullable=False)
    priority = Column(pg_req_priority, default=RequirementPriority.MANDATORY.value)
    description = Column(Text, nullable=False)
    raw_text = Column(Text)
    deadline = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    tender = relationship("TenderModel", back_populates="requirements")
