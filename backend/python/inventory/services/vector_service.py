from __future__ import annotations

from typing import Any, Optional

from inventory.domain.exceptions import ValidationError
from inventory.ports.embedding_provider import EmbeddingProvider
from inventory.ports.logger import ProductLogger
from inventory.ports.product_repository import ProductRepository
from inventory.ports.vector_repository import VectorRepository


class VectorService:

    DEFAULT_TOP_K = 10
    MAX_TOP_K = 50

    def __init__(
        self,
        vector_repository: VectorRepository,
        product_repository: ProductRepository,
        embedding_provider: EmbeddingProvider,
        logger: ProductLogger,
    ) -> None:
        self._vector_repo = vector_repository
        self._product_repo = product_repository
        self._embedding_provider = embedding_provider
        self._logger = logger

    def top_k_similar_products(
        self,
        *,
        product_id: Optional[str] = None,
        query: Optional[str] = None,
        top_k: Optional[Any] = None,
        score_threshold: Optional[float] = None,
        category: Optional[str] = None,
    ) -> list[dict]:
        scored = self.top_k_similar_products_with_scores(
            product_id=product_id,
            query=query,
            top_k=top_k,
            score_threshold=score_threshold,
            category=category,
        )
        return [item['product'] for item in scored]

    def top_k_similar_products_with_scores(
        self,
        *,
        product_id: Optional[str] = None,
        query: Optional[str] = None,
        top_k: Optional[Any] = None,
        score_threshold: Optional[float] = None,
        category: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        self._logger.debug(
            'top_k_similar_products_with_scores called',
            product_id=product_id,
            query=query,
            top_k=top_k,
            score_threshold=score_threshold,
            category=category,
        )
        mode = self._resolve_mode(product_id=product_id, query=query)
        k = self._validate_top_k(top_k)
        category = self._normalize_category(category)

        if mode == "id":
            results = self._vector_repo.search_by_id(
                vector_id=str(product_id),
                limit=k,
                score_threshold=score_threshold,
                category=category,
            )
            self._logger.debug('Vector search by id completed', product_id=product_id, results_count=len(results))
        else:
            assert query is not None
            embedding = self._embed_query(query)
            if not embedding:
                self._logger.warning('Query embedding resulted in empty vector', query=query)
                return []
            self._logger.debug('Calling vector search with embedding', embedding_dim=len(embedding), limit=k, score_threshold=score_threshold, category=category)
            results = self._vector_repo.search(
                embedding=embedding,
                limit=k,
                score_threshold=score_threshold,
                category=category,
            )
            self._logger.debug('Vector search by query completed', query=query, results_count=len(results))

        ids_in_order = [r.vector_id for r in results]
        self._logger.debug('Extracted vector ids from results', ids_count=len(ids_in_order), ids=ids_in_order[:10])
        products_by_id = self._product_repo.get_many_by_ids(ids_in_order)
        self._logger.debug('Retrieved products from repository', retrieved_count=len(products_by_id), requested_count=len(ids_in_order))

        scored_products: list[dict[str, Any]] = []
        for result in results:
            product = products_by_id.get(result.vector_id)
            if not product:
                continue
            scored_products.append(
                {
                    'product': product,
                    'score': float(result.score),
                    'vector_id': result.vector_id,
                }
            )
        self._logger.debug('Hydrated scored products in order', hydrated_count=len(scored_products))

        missing = [pid for pid in ids_in_order if pid not in products_by_id]
        if missing:
            self._logger.warning(
                "Vector search returned ids not found in product store",
                missing_count=len(missing),
                missing_ids=missing[:10],
            )

        self._logger.info(
            'top_k_similar_products_with_scores completed',
            mode=mode,
            total_results=len(scored_products),
            missing_count=len(missing),
        )
        return scored_products

    def _resolve_mode(self, *, product_id: Optional[str], query: Optional[str]) -> str:
        if product_id and query:
            self._logger.error('Both product_id and query provided', product_id=product_id, query=query)
            raise ValidationError("Provide exactly one of 'product_id' or 'query'")
        if product_id:
            return "id"
        if query is not None:
            return "query"
        self._logger.error('Neither product_id nor query provided')
        raise ValidationError("Provide exactly one of 'product_id' or 'query'")

    def _normalize_category(self, category: Optional[str]) -> Optional[str]:
        if category is None:
            return None
        normalized = category.strip().lower()
        return normalized or None

    def _embed_query(self, query: str) -> list[float]:
        q = query.strip()
        if not q:
            self._logger.error('Empty query provided')
            raise ValidationError("'query' must not be empty")

        self._logger.debug('Embedding query', query_length=len(q))
        # The e5-base-v2 model requires "query: " prefix for search queries.
        embeddings = self._embedding_provider.generate_embeddings([q], text_type="query")

        if not embeddings or not embeddings[0]:
            self._logger.warning('Embedding provider returned empty embedding')
            return []
        self._logger.debug('Query embedding generated successfully', embedding_dim=len(embeddings[0]))
        return embeddings[0]

    def _validate_top_k(self, raw_top_k: Optional[Any]) -> int:
        if raw_top_k is None or raw_top_k == "":
            self._logger.debug('top_k not provided, using default', default_top_k=self.DEFAULT_TOP_K)
            return self.DEFAULT_TOP_K
        try:
            k = int(raw_top_k)
        except (TypeError, ValueError):
            self._logger.error('Invalid top_k value', raw_top_k=raw_top_k, error='Cannot convert to integer')
            raise ValidationError("'top_k' must be an integer")
        if k <= 0:
            self._logger.error('top_k must be positive', top_k=k)
            raise ValidationError("'top_k' must be > 0")
        if k > self.MAX_TOP_K:
            self._logger.error('top_k exceeds maximum', top_k=k, max_top_k=self.MAX_TOP_K)
            raise ValidationError(f"'top_k' must be <= {self.MAX_TOP_K}")
        self._logger.debug('top_k validated', top_k=k)
        return k
