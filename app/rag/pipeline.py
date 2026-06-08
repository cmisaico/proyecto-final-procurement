from typing import List, Optional

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

from app.core.config import settings
from app.core.llm_factory import get_llm
from app.core.logging import get_logger
from app.core.tracing import span
from app.infrastructure.vector_store.qdrant_client import qdrant_store
from app.services.embedding_service import EmbeddingService

logger = get_logger(__name__)

RAG_PROMPT = ChatPromptTemplate.from_messages([
    ("system", (
        "Eres un asistente experto en análisis de licitaciones públicas. "
        "Usa el contexto provisto para responder la pregunta del usuario. "
        "Si la información no está en el contexto, indícalo claramente. "
        "Responde siempre en el idioma de la pregunta.\n\n"
        "CONTEXTO:\n{context}"
    )),
    ("human", "{question}"),
])


class RAGPipeline:
    def __init__(self):
        self._embedding_service = EmbeddingService()
        self._llm = get_llm(temperature=0.1)
        self._chain = RAG_PROMPT | self._llm | StrOutputParser()

    async def query(
        self,
        question: str,
        tender_id: Optional[str] = None,
        document_id: Optional[str] = None,
        top_k: int = 5,
    ) -> dict:
        with span("rag.embed_query"):
            query_vector = await self._embedding_service.embed_query(question)

        with span("rag.vector_search"):
            results = qdrant_store.search(
                query_vector=query_vector,
                top_k=top_k,
                tender_id=tender_id,
                document_id=document_id,
            )

        context_parts = []
        sources = []
        for hit in results:
            payload = hit.payload or {}
            context_parts.append(payload.get("content", ""))
            sources.append({
                "chunk_id": payload.get("chunk_id"),
                "document_id": payload.get("document_id"),
                "page_number": payload.get("page_number"),
                "score": hit.score,
            })

        context = "\n\n---\n\n".join(context_parts)
        logger.info("RAG query", extra={"question": question[:80], "chunks_retrieved": len(results)})

        with span("rag.llm_generate"):
            answer = await self._chain.ainvoke({"context": context, "question": question})

        return {
            "answer": answer,
            "sources": sources,
            "question": question,
        }
