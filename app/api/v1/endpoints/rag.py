from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.exceptions import AppException
from app.rag.pipeline import RAGPipeline

router = APIRouter(prefix="/rag", tags=["rag"])


class QueryRequest(BaseModel):
    question: str
    tender_id: Optional[str] = None
    document_id: Optional[str] = None
    top_k: int = 5


class SourceItem(BaseModel):
    chunk_id: Optional[str]
    document_id: Optional[str]
    page_number: Optional[int]
    score: float


class QueryResponse(BaseModel):
    answer: str
    question: str
    sources: List[SourceItem]


@router.post("/query", response_model=QueryResponse)
async def query_rag(body: QueryRequest):
    pipeline = RAGPipeline()
    try:
        result = await pipeline.query(
            question=body.question,
            tender_id=body.tender_id,
            document_id=body.document_id,
            top_k=body.top_k,
        )
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)

    return QueryResponse(
        answer=result["answer"],
        question=result["question"],
        sources=[SourceItem(**s) for s in result["sources"]],
    )
