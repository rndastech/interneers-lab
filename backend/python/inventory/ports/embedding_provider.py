from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any, List


class EmbeddingProvider(ABC):

    @abstractmethod
    def generate_embeddings(self, texts: List[str], text_type: str = "passage") -> List[List[float]]:
        pass

    @abstractmethod
    def get_embedding_dimension(self) -> int:
        pass
