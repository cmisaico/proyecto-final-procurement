from typing import List, Optional
import uuid

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    PointStruct,
    VectorParams,
    Filter,
    FieldCondition,
    MatchValue,
    ScoredPoint,
)

from app.core.config import settings
from app.core.exceptions import VectorStoreException
from app.core.logging import get_logger

logger = get_logger(__name__)


class QdrantVectorStore:
    def __init__(self):
        self._client = QdrantClient(
            host=settings.QDRANT_HOST,
            port=settings.QDRANT_PORT,
        )
        self._collection = settings.QDRANT_COLLECTION

    def ensure_collection(self) -> None:
        try:
            collections = [c.name for c in self._client.get_collections().collections]
            if self._collection not in collections:
                self._client.create_collection(
                    collection_name=self._collection,
                    vectors_config=VectorParams(
                        size=settings.EMBEDDING_DIMENSION,
                        distance=Distance.COSINE,
                    ),
                )
                logger.info("Qdrant collection created", extra={"collection": self._collection})
        except Exception as e:
            raise VectorStoreException(str(e))

    def upsert_chunks(self, chunk_ids: List[str], embeddings: List[List[float]], payloads: List[dict]) -> None:
        try:
            self.ensure_collection()
            points = [
                PointStruct(
                    id=str(uuid.uuid5(uuid.NAMESPACE_DNS, cid)),
                    vector=emb,
                    payload=payload,
                )
                for cid, emb, payload in zip(chunk_ids, embeddings, payloads)
            ]
            self._client.upsert(collection_name=self._collection, points=points)
            logger.info("Chunks upserted to Qdrant", extra={"count": len(points)})
        except Exception as e:
            raise VectorStoreException(str(e))

    def search(
        self,
        query_vector: List[float],
        top_k: int = 5,
        document_id: Optional[str] = None,
        tender_id: Optional[str] = None,
    ) -> List[ScoredPoint]:
        try:
            query_filter = None
            conditions = []
            if document_id:
                conditions.append(FieldCondition(key="document_id", match=MatchValue(value=document_id)))
            if tender_id:
                conditions.append(FieldCondition(key="tender_id", match=MatchValue(value=tender_id)))
            if conditions:
                query_filter = Filter(must=conditions)

            return self._client.search(
                collection_name=self._collection,
                query_vector=query_vector,
                limit=top_k,
                query_filter=query_filter,
                with_payload=True,
            )
        except Exception as e:
            raise VectorStoreException(str(e))

    def delete_by_document(self, document_id: str) -> None:
        try:
            self._client.delete(
                collection_name=self._collection,
                points_selector=Filter(
                    must=[FieldCondition(key="document_id", match=MatchValue(value=document_id))]
                ),
            )
        except Exception as e:
            raise VectorStoreException(str(e))


qdrant_store = QdrantVectorStore()
