from __future__ import annotations

from contextlib import nullcontext
from typing import Any, Optional

from inventory.adapters.langsmith_tracer import LangSmithTracer
from inventory.domain.exceptions import ValidationError
from inventory.domain.schemas import RetrievedChunkSchema
from inventory.ports.embedding_provider import EmbeddingProvider
from inventory.ports.logger import ProductLogger
from inventory.ports.product_repository import ProductRepository
from inventory.ports.rag_retriever import RAGRetriever
from inventory.ports.vector_repository import VectorRepository


class RAGRetrievalService(RAGRetriever):

    DEFAULT_TOP_K = 3
    MAX_TOP_K = 20
    KNOWLEDGE_WEIGHT = 1.0
    PRODUCT_WEIGHT = 0.65

    def __init__(
        self,
        knowledge_vector_repository: VectorRepository,
        product_vector_repository: VectorRepository,
        product_repository: ProductRepository,
        embedding_provider: EmbeddingProvider,
        logger: ProductLogger,
        *,
        default_top_k: int = DEFAULT_TOP_K,
        max_top_k: int = MAX_TOP_K,
        tracer: Optional[LangSmithTracer] = None,
        trace_project: Optional[str] = None,
    ) -> None:
        self._knowledge_vector_repo = knowledge_vector_repository
        self._product_vector_repo = product_vector_repository
        self._product_repo = product_repository
        self._embedding_provider = embedding_provider
        self._logger = logger
        self._default_top_k = default_top_k
        self._max_top_k = max_top_k
        self._tracer = tracer
        self._trace_project = trace_project

    def retrieve_relevant_chunks(
        self,
        query: str,
        top_k: int = 3,
        category: Optional[str] = None,
        include_product_context: bool = True,
    ) -> list[RetrievedChunkSchema]:
        normalized_query = self._normalize_query(query)
        k = self._validate_top_k(top_k)
        normalized_category = self._normalize_category(category)

        with self._trace(
            name="rag.retrieve_relevant_chunks",
            metadata={
                "component": "RAGRetrievalService",
                "include_product_context": include_product_context,
                "category": normalized_category,
                "top_k": k,
            },
            inputs={
                "query": normalized_query,
                "top_k": k,
                "category": normalized_category,
                "include_product_context": include_product_context,
            },
        ):
            embedding = self._embed_query(normalized_query)

            knowledge_candidates = self._knowledge_candidates(
                query=normalized_query,
                embedding=embedding,
                limit=max(k * 2, k),
            )

            product_candidates: list[dict[str, Any]] = []
            if include_product_context:
                product_candidates = self._product_candidates(
                    embedding=embedding,
                    limit=max(k, self._default_top_k),
                    category=normalized_category,
                )

            merged = self._merge_candidates(knowledge_candidates, product_candidates, k)
        self._logger.info(
            "retrieve_relevant_chunks completed",
            query=normalized_query,
            top_k=k,
            category=normalized_category,
            include_product_context=include_product_context,
            knowledge_candidates=len(knowledge_candidates),
            product_candidates=len(product_candidates),
            returned_count=len(merged),
        )
        return merged

    def _normalize_query(self, query: str) -> str:
        normalized = (query or "").strip()
        if not normalized:
            raise ValidationError("'query' must not be empty")
        return normalized

    def _validate_top_k(self, raw_top_k: Any) -> int:
        if raw_top_k in (None, ""):
            return self._default_top_k
        try:
            k = int(raw_top_k)
        except (TypeError, ValueError):
            raise ValidationError("'top_k' must be an integer")
        if k <= 0:
            raise ValidationError("'top_k' must be > 0")
        if k > self._max_top_k:
            raise ValidationError(f"'top_k' must be <= {self._max_top_k}")
        return k

    @staticmethod
    def _normalize_category(category: Optional[str]) -> Optional[str]:
        if category is None:
            return None
        normalized = category.strip().lower()
        return normalized or None

    def _embed_query(self, query: str) -> list[float]:
        self._logger.debug("Embedding query for RAG retrieval", query_length=len(query))
        embeddings = self._embedding_provider.generate_embeddings([query], text_type="query")
        if not embeddings or not embeddings[0]:
            raise ValidationError("Embedding provider returned an empty query embedding")
        return embeddings[0]

    def _knowledge_candidates(
        self,
        *,
        query: str,
        embedding: list[float],
        limit: int,
    ) -> list[dict[str, Any]]:
        results = self._knowledge_vector_repo.search(embedding=embedding, limit=limit)
        candidates: list[dict[str, Any]] = []

        for idx, result in enumerate(results):
            metadata = result.metadata or {}
            content = str(metadata.get("content", "")).strip()
            if not content:
                continue

            source_id = str(metadata.get("source_id") or metadata.get("file_name") or "knowledge")
            source_name = str(metadata.get("source_name") or source_id.replace("_", " ").title())
            chunk_id = str(metadata.get("chunk_id") or result.vector_id)

            raw_score = self._normalize_score(result.score)
            lexical_bonus = self._keyword_bonus(query, f"{source_id} {source_name} {content[:240]}")
            weighted_score = min(1.0, raw_score * self.KNOWLEDGE_WEIGHT + lexical_bonus)

            candidates.append(
                {
                    "source_id": source_id,
                    "source_name": source_name,
                    "chunk_id": chunk_id,
                    "content": content,
                    "score": weighted_score,
                    "metadata": {
                        **metadata,
                        "doc_type": "knowledge",
                        "vector_id": result.vector_id,
                        "raw_score": raw_score,
                        "weighted_score": weighted_score,
                        "rank": idx + 1,
                    },
                }
            )

        return candidates

    def _product_candidates(
        self,
        *,
        embedding: list[float],
        limit: int,
        category: Optional[str],
    ) -> list[dict[str, Any]]:
        results = self._product_vector_repo.search(
            embedding=embedding,
            limit=limit,
            category=category,
        )

        ids_in_order = [r.vector_id for r in results]
        products_by_id = self._product_repo.get_many_by_ids(ids_in_order)

        candidates: list[dict[str, Any]] = []
        for idx, result in enumerate(results):
            product = products_by_id.get(result.vector_id)
            if not product:
                continue

            product_id = str(product.get("id") or result.vector_id)
            source_id = f"product::{product_id}"
            source_name = str(product.get("name") or "Product Context")
            chunk_id = source_id
            content = self._product_context_text(product)
            if not content:
                continue

            raw_score = self._normalize_score(result.score)
            weighted_score = min(1.0, raw_score * self.PRODUCT_WEIGHT)

            candidates.append(
                {
                    "source_id": source_id,
                    "source_name": source_name,
                    "chunk_id": chunk_id,
                    "content": content,
                    "score": weighted_score,
                    "metadata": {
                        "doc_type": "product",
                        "product_id": product_id,
                        "category": product.get("category"),
                        "brand": product.get("brand"),
                        "price": str(product.get("price", "")),
                        "vector_id": result.vector_id,
                        "raw_score": raw_score,
                        "weighted_score": weighted_score,
                        "rank": idx + 1,
                    },
                }
            )

        return candidates

    @staticmethod
    def _product_context_text(product: dict[str, Any]) -> str:
        fields = [
            f"Name: {product.get('name', '')}",
            f"Description: {product.get('description', '')}",
            f"Category: {product.get('category', '')}",
            f"Brand: {product.get('brand', '')}",
            f"Price: {product.get('price', '')}",
            f"Quantity: {product.get('quantity', '')}",
        ]
        return "\n".join([f for f in fields if f.strip()]).strip()

    def _merge_candidates(
        self,
        knowledge_candidates: list[dict[str, Any]],
        product_candidates: list[dict[str, Any]],
        top_k: int,
    ) -> list[RetrievedChunkSchema]:
        combined = knowledge_candidates + product_candidates
        if not combined:
            return []

        def sort_key(candidate: dict[str, Any]) -> tuple[float, int]:
            doc_type = str(candidate.get("metadata", {}).get("doc_type", ""))
            type_priority = 1 if doc_type == "knowledge" else 0
            return (float(candidate.get("score", 0.0)), type_priority)

        sorted_candidates = sorted(combined, key=sort_key, reverse=True)

        unique_results: list[RetrievedChunkSchema] = []
        seen_chunk_ids: set[str] = set()

        for candidate in sorted_candidates:
            chunk_id = str(candidate.get("chunk_id", "")).strip()
            if not chunk_id or chunk_id in seen_chunk_ids:
                continue
            seen_chunk_ids.add(chunk_id)
            unique_results.append(RetrievedChunkSchema(**candidate))
            if len(unique_results) >= top_k:
                break

        return unique_results

    @staticmethod
    def _normalize_score(score: float) -> float:
        try:
            value = float(score)
        except (TypeError, ValueError):
            return 0.0

        if 0.0 <= value <= 1.0:
            return value
        if -1.0 <= value < 0.0:
            return (value + 1.0) / 2.0
        if value < 0.0:
            return 0.0
        return 1.0

    @staticmethod
    def _keyword_bonus(query: str, text: str) -> float:
        query_tokens = {t for t in query.lower().split() if len(t) >= 4}
        if not query_tokens:
            return 0.0
        text_lower = text.lower()
        matches = sum(1 for token in query_tokens if token in text_lower)
        return min(0.15, matches * 0.03)

    def _trace(self, *, name: str, metadata: dict[str, Any], inputs: dict[str, Any]):
        if not self._tracer:
            return nullcontext()
        return self._tracer.trace(
            name=name,
            project_name=self._trace_project,
            metadata=metadata,
            inputs=inputs,
        )
