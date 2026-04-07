from dataclasses import dataclass
from typing import List, Dict, Any


@dataclass
class VectorDocument:
    vector_id: str
    embedding: List[float]
    metadata: Dict[str, Any]


@dataclass
class SearchResult:
    vector_id: str
    metadata: Dict[str, Any]
    score: float
