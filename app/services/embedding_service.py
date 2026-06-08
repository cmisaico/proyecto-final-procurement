from typing import List

from app.core.llm_factory import get_embeddings
from app.core.logging import get_logger

logger = get_logger(__name__)


class EmbeddingService:
    def __init__(self):
        self._embeddings = get_embeddings()

    async def embed_texts(self, texts: List[str]) -> List[List[float]]:
        logger.info("Generating embeddings", extra={"count": len(texts)})
        vectors = await self._embeddings.aembed_documents(texts)
        return vectors

    async def embed_query(self, text: str) -> List[float]:
        return await self._embeddings.aembed_query(text)
