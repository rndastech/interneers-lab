from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from inventory.domain.schemas import RetrievedChunkSchema


class RAGRetriever(ABC):

    @abstractmethod
    def retrieve_relevant_chunks(
        self,
        query: str,
        top_k: int = 3,
        category: Optional[str] = None,
        include_product_context: bool = True,
    ) -> list[RetrievedChunkSchema]:
        raise NotImplementedError
