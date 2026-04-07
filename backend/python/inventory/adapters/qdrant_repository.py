from __future__ import annotations
import uuid
from typing import Any, Optional, cast
from django.conf import settings
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointIdsList,
    PointStruct,
    VectorParams,
    ExtendedPointId,
)
from inventory.domain.vector import SearchResult, VectorDocument
from inventory.ports.vector_repository import VectorRepository


class QdrantVectorRepository(VectorRepository):
    def __init__(self, url: str, collection_name: str, vector_size: int, api_key: Optional[str] = None):
        self.client = QdrantClient(url=url, api_key=api_key)
        self.collection_name = collection_name
        self.vector_size = vector_size
        self._ensure_collection_exists()

    def _ensure_collection_exists(self) -> None:
        if not self.client.collection_exists(self.collection_name):
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(size=self.vector_size, distance=Distance.COSINE),
            )

    @staticmethod
    def _to_qdrant_id(vector_id: str) -> str:
        return str(uuid.uuid5(uuid.NAMESPACE_DNS, vector_id))

    @staticmethod
    def _category_filter(category: Optional[str]) -> Optional[Filter]:
        if not category:
            return None
        return Filter(must=[FieldCondition(key="category", match=MatchValue(value=category))])

    @staticmethod
    def _normalize_vector(vector: Any) -> list[float]:
        if vector is None:
            return []
        if isinstance(vector, dict):
            return cast(list[float], next(iter(vector.values())))
        return cast(list[float], vector)

    def _make_point(self, doc: VectorDocument) -> PointStruct:
        return PointStruct(
            id=self._to_qdrant_id(doc.vector_id),
            vector=doc.embedding,
            payload={"vector_id": doc.vector_id, **(doc.metadata or {})},
        )

    @staticmethod
    def _to_search_result(scored_point: Any) -> Optional[SearchResult]:
        payload = dict(scored_point.payload or {})
        vector_id = payload.pop("vector_id", None)
        if not vector_id:
            return None
        return SearchResult(vector_id=vector_id, metadata=payload, score=scored_point.score)

    def upsert(self, document: VectorDocument) -> str:
        self.client.upsert(
            collection_name=self.collection_name,
            points=[self._make_point(document)],
        )
        return document.vector_id

    def upsert_batch(self, documents: list[VectorDocument]) -> tuple[list[str], list[str]]:
        points = [self._make_point(doc) for doc in documents]
        try:
            self.client.upsert(collection_name=self.collection_name, points=points)
            return [doc.vector_id for doc in documents], []
        except Exception:
            return [], [doc.vector_id for doc in documents]

    def delete(self, vector_id: str) -> bool:
        qid: ExtendedPointId = self._to_qdrant_id(vector_id)
        try:
            self.client.delete(
                collection_name=self.collection_name,
                points_selector=PointIdsList(points=[qid]),
            )
            return True
        except Exception:
            return False

    def delete_batch(self, vector_ids: list[str]) -> tuple[int, int]:
        qids: list[ExtendedPointId] = [self._to_qdrant_id(v) for v in vector_ids]
        try:
            self.client.delete(
                collection_name=self.collection_name,
                points_selector=PointIdsList(points=qids),
            )
            return len(vector_ids), 0
        except Exception:
            return 0, len(vector_ids)

    def update_metadata(self, vector_id: str, metadata: dict[str, Any]) -> bool:
        qid: ExtendedPointId = self._to_qdrant_id(vector_id)
        try:
            self.client.set_payload(
                collection_name=self.collection_name,
                payload=metadata,
                points=[qid],
            )
            return True
        except Exception:
            return False

    def clear(self) -> bool:
        try:
            self.client.delete_collection(collection_name=self.collection_name)
            self._ensure_collection_exists()
            return True
        except Exception:
            return False

    def get(self, vector_id: str) -> Optional[VectorDocument]:
        try:
            points = self.client.retrieve(
                collection_name=self.collection_name,
                ids=[self._to_qdrant_id(vector_id)],
                with_vectors=True,
            )
            if not points:
                return None

            point = points[0]
            payload = dict(point.payload or {})
            payload.pop("vector_id", None)
            vector = self._normalize_vector(point.vector)

            return VectorDocument(
                vector_id=vector_id,
                embedding=vector,
                metadata=payload,
            )
        except Exception:
            return None

    def exists(self, vector_id: str) -> bool:
        try:
            points = self.client.retrieve(
                collection_name=self.collection_name,
                ids=[self._to_qdrant_id(vector_id)],
                with_vectors=False,
            )
            return bool(points)
        except Exception:
            return False

    def count(self) -> int:
        try:
            info = self.client.get_collection(self.collection_name)
            return info.points_count or 0
        except Exception:
            return 0

    def search(
        self,
        embedding: list[float],
        limit: int = 10,
        score_threshold: Optional[float] = None,
        category: Optional[str] = None,
    ) -> list[SearchResult]:
        # client.search() is removed in v1.17+; use query_points() instead
        response = self.client.query_points(
            collection_name=self.collection_name,
            query=embedding,
            limit=limit,
            score_threshold=score_threshold,
            query_filter=self._category_filter(category),
        )
        return [r for sp in response.points if (r := self._to_search_result(sp))]

    def search_by_id(
        self,
        vector_id: str,
        limit: int = 10,
        score_threshold: Optional[float] = None,
        category: Optional[str] = None,
    ) -> list[SearchResult]:
        # client.recommend() is removed in v1.17+; passing a point UUID string
        # to query_points(query=) triggers the same "recommend by ID" behaviour
        response = self.client.query_points(
            collection_name=self.collection_name,
            query=self._to_qdrant_id(vector_id),   # UUID str → recommend strategy
            limit=limit + 1,                        # +1 because the source point itself may appear
            score_threshold=score_threshold,
            query_filter=self._category_filter(category),
        )
        return [
            r
            for sp in response.points
            if (r := self._to_search_result(sp)) and r.vector_id != vector_id
        ][:limit]


vector_repository = QdrantVectorRepository(
    url=settings.QDRANT_URL,
    collection_name=settings.QDRANT_COLLECTION_NAME,
    vector_size=settings.QDRANT_VECTOR_SIZE,
    api_key=settings.QDRANT_API_KEY,
)