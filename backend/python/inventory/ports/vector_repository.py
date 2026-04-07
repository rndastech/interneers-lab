from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
from inventory.domain.vector import VectorDocument, SearchResult


class VectorRepository(ABC):

    @abstractmethod
    def upsert(self, document: VectorDocument) -> str:
        raise NotImplementedError

    @abstractmethod
    def upsert_batch(self, documents: List[VectorDocument]) -> tuple[List[str], List[str]]:
        raise NotImplementedError

    @abstractmethod
    def search(
        self,
        embedding: List[float],
        limit: int = 10,
        score_threshold: Optional[float] = None,
        category: Optional[str] = None,
    ) -> List[SearchResult]:
        raise NotImplementedError

    @abstractmethod
    def search_by_id(
        self,
        vector_id: str,
        limit: int = 10,
        score_threshold: Optional[float] = None,
        category: Optional[str] = None,
    ) -> List[SearchResult]:
        raise NotImplementedError

    @abstractmethod
    def get(self, vector_id: str) -> Optional[VectorDocument]:
        raise NotImplementedError

    @abstractmethod
    def delete(self, vector_id: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def delete_batch(self, vector_ids: List[str]) -> tuple[int, int]:
        raise NotImplementedError

    @abstractmethod
    def update_metadata(self, vector_id: str, metadata: Dict[str, Any]) -> bool:
        raise NotImplementedError

    @abstractmethod
    def exists(self, vector_id: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def count(self) -> int:
        raise NotImplementedError

    @abstractmethod
    def clear(self) -> bool:
        raise NotImplementedError

