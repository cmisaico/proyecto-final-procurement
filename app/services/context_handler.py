from typing import List, Optional
import tiktoken

from app.core.config import settings
from app.core.logging import get_logger
from app.infrastructure.vector_store.qdrant_client import qdrant_store
from app.services.embedding_service import EmbeddingService

logger = get_logger(__name__)

# Approximate tokenizer (cl100k_base is close enough for qwen2.5)
try:
    _enc = tiktoken.get_encoding("cl100k_base")
except Exception:
    _enc = None


def _count_tokens(text: str) -> int:
    if _enc:
        return len(_enc.encode(text))
    return len(text) // 4  # rough fallback: 4 chars ≈ 1 token


class ContextResult:
    def __init__(self, content: str, document_id: str, page_number: Optional[int], score: float):
        self.content = content
        self.document_id = document_id
        self.page_number = page_number
        self.score = score

    def __repr__(self):
        return f"ContextResult(score={self.score:.3f}, tokens={_count_tokens(self.content)})"


class EfficientContextHandler:
    """
    Efficient Context Handling Pattern:
    - Semantic Retrieval from Qdrant
    - Top-K filtering
    - Token budget enforcement (context compression)
    - Score-based ranking
    """

    def __init__(self):
        self._embedder = EmbeddingService()
        self._top_k = settings.CONTEXT_TOP_K
        self._max_tokens = settings.MAX_CONTEXT_TOKENS

    async def retrieve(
        self,
        query: str,
        tender_id: Optional[str] = None,
        document_id: Optional[str] = None,
        top_k: Optional[int] = None,
        max_tokens: Optional[int] = None,
    ) -> List[ContextResult]:
        k = top_k or self._top_k
        budget = max_tokens or self._max_tokens

        query_vector = await self._embedder.embed_query(query)
        hits = qdrant_store.search(
            query_vector=query_vector,
            top_k=k,
            tender_id=tender_id,
            document_id=document_id,
        )

        # Sort descending by score
        hits = sorted(hits, key=lambda h: h.score, reverse=True)

        results: List[ContextResult] = []
        token_used = 0

        for hit in hits:
            payload = hit.payload or {}
            content = payload.get("content", "")
            tokens = _count_tokens(content)

            if token_used + tokens > budget:
                # Truncate if it fits partially
                remaining = budget - token_used
                if remaining > 50:
                    content = content[: remaining * 4]  # rough char truncation
                    tokens = remaining
                else:
                    break

            results.append(ContextResult(
                content=content,
                document_id=payload.get("document_id", ""),
                page_number=payload.get("page_number"),
                score=hit.score,
            ))
            token_used += tokens

        logger.info(
            "Context retrieved",
            extra={
                "query": query[:60],
                "chunks": len(results),
                "tokens_used": token_used,
                "budget": budget,
            },
        )
        return results

    async def retrieve_multi(
        self,
        queries: List[str],
        tender_id: Optional[str] = None,
        top_k_per_query: int = 3,
    ) -> List[ContextResult]:
        """Retrieve context for multiple queries, deduplicate, re-rank."""
        seen_contents: set = set()
        all_results: List[ContextResult] = []

        for q in queries:
            results = await self.retrieve(
                query=q,
                tender_id=tender_id,
                top_k=top_k_per_query,
                max_tokens=self._max_tokens // len(queries),
            )
            for r in results:
                if r.content not in seen_contents:
                    seen_contents.add(r.content)
                    all_results.append(r)

        # Re-rank by score
        all_results.sort(key=lambda r: r.score, reverse=True)
        return all_results

    def format_context(self, results: List[ContextResult]) -> str:
        parts = []
        for i, r in enumerate(results, 1):
            parts.append(f"[Fragmento {i} | Página {r.page_number} | Score {r.score:.2f}]\n{r.content}")
        return "\n\n---\n\n".join(parts)
