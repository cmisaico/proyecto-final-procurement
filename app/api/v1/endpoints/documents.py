from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.use_cases.process_document import ProcessDocumentInput, ProcessDocumentUseCase
from app.application.use_cases.upload_document import UploadDocumentInput, UploadDocumentUseCase
from app.core.exceptions import AppException, DocumentNotFoundException
from app.infrastructure.database.connection import get_db
from app.infrastructure.repositories.pg_document_repository import PgDocumentRepository

router = APIRouter(prefix="/documents", tags=["documents"])


class UploadResponse(BaseModel):
    document_id: str
    tender_id: str
    filename: str
    minio_path: str
    file_size: int


class ProcessResponse(BaseModel):
    document_id: str
    page_count: int
    chunk_count: int
    status: str


class DocumentResponse(BaseModel):
    id: str
    tender_id: str
    filename: str
    original_filename: str
    minio_path: str
    file_size: int
    status: str
    page_count: int


@router.post("/upload", response_model=UploadResponse, status_code=201)
async def upload_document(
    tender_id: str = Form(...),
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_db),
):
    content = await file.read()
    use_case = UploadDocumentUseCase(session)
    try:
        result = await use_case.execute(
            UploadDocumentInput(
                tender_id=tender_id,
                filename=file.filename,
                content=content,
                content_type=file.content_type or "application/pdf",
            )
        )
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    return UploadResponse(**result.__dict__)


@router.post("/process", response_model=ProcessResponse)
async def process_document(
    document_id: str,
    session: AsyncSession = Depends(get_db),
):
    use_case = ProcessDocumentUseCase(session)
    try:
        result = await use_case.execute(ProcessDocumentInput(document_id=document_id))
    except DocumentNotFoundException as e:
        raise HTTPException(status_code=404, detail=e.message)
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    return ProcessResponse(**result.__dict__)


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: str,
    session: AsyncSession = Depends(get_db),
):
    repo = PgDocumentRepository(session)
    doc = await repo.get_by_id(document_id)
    if not doc:
        raise HTTPException(status_code=404, detail=f"Document {document_id} not found")
    return DocumentResponse(
        id=doc.id,
        tender_id=doc.tender_id,
        filename=doc.filename,
        original_filename=doc.original_filename,
        minio_path=doc.minio_path,
        file_size=doc.file_size,
        status=doc.status.value,
        page_count=doc.page_count,
    )
