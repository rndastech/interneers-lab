import argparse
import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), "../../"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "django_app.settings")

import django

django.setup()

from django.conf import settings

from inventory.adapters.e5_base_instruct import embedding_provider
from inventory.adapters.langsmith_tracer import LangSmithTracer
from inventory.adapters.product_repository import product_repository
from inventory.adapters.python_logger import PythonProductLogger
from inventory.adapters.qdrant_repository import QdrantVectorRepository
from inventory.services.rag_retrieval_service import RAGRetrievalService
from inventory.tests.rag_retrieval_eval_set import (
    MANDATORY_RETURN_POLICY_QUERY,
    RAG_RETRIEVAL_EVAL_SET,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate RAG chunk retrieval quality")
    parser.add_argument("--k", type=int, default=settings.RAG_RETRIEVAL_TOP_K, help="Top K retrieved chunks")
    parser.add_argument(
        "--max-top-k",
        type=int,
        default=settings.RAG_RETRIEVAL_MAX_TOP_K,
        help="Maximum supported top-k for retrieval service validation",
    )
    parser.add_argument(
        "--knowledge-collection",
        type=str,
        default=settings.RAG_QDRANT_COLLECTION_NAME,
        help="Qdrant collection name for knowledge chunks",
    )
    parser.add_argument(
        "--product-collection",
        type=str,
        default=settings.QDRANT_COLLECTION_NAME,
        help="Qdrant collection name for product vectors",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail with non-zero exit code if mandatory acceptance checks do not pass",
    )
    return parser.parse_args()


def metric_bundle(results: list, expected_source_ids: list[str], expected_phrases: list[str], k: int) -> dict:
    top_results = results[:k]
    source_ids = [str(r.source_id) for r in top_results]

    hits = sum(1 for source_id in source_ids if source_id in expected_source_ids)
    precision = hits / k if k > 0 else 0.0
    recall = hits / len(expected_source_ids) if expected_source_ids else 0.0

    rr = 0.0
    for i, source_id in enumerate(source_ids):
        if source_id in expected_source_ids:
            rr = 1.0 / (i + 1)
            break

    joined_content = "\n".join(str(r.content).lower() for r in top_results)
    phrase_hits = sum(1 for phrase in expected_phrases if phrase.lower() in joined_content)
    phrase_coverage = phrase_hits / len(expected_phrases) if expected_phrases else 1.0

    return {
        "precision": precision,
        "recall": recall,
        "rr": rr,
        "source_hit": hits > 0,
        "phrase_coverage": phrase_coverage,
        "source_ids": source_ids,
    }


def build_retrieval_service(args: argparse.Namespace) -> RAGRetrievalService:
    logger = PythonProductLogger("inventory.tests.evaluate_rag_retrieval")
    tracer = LangSmithTracer(
        api_key=settings.LANGSMITH_API_KEY,
        endpoint=settings.LANGSMITH_ENDPOINT,
        default_project=settings.LANGSMITH_EVAL_PROJECT,
        enabled=settings.LANGSMITH_TRACING,
        logger=logger,
    )

    knowledge_repo = QdrantVectorRepository(
        url=settings.QDRANT_URL,
        collection_name=args.knowledge_collection,
        vector_size=settings.QDRANT_VECTOR_SIZE,
        api_key=settings.QDRANT_API_KEY,
    )
    product_repo = QdrantVectorRepository(
        url=settings.QDRANT_URL,
        collection_name=args.product_collection,
        vector_size=settings.QDRANT_VECTOR_SIZE,
        api_key=settings.QDRANT_API_KEY,
    )

    return RAGRetrievalService(
        knowledge_vector_repository=knowledge_repo,
        product_vector_repository=product_repo,
        product_repository=product_repository,
        embedding_provider=embedding_provider,
        logger=logger,
        default_top_k=args.k,
        max_top_k=args.max_top_k,
        tracer=tracer,
        trace_project=settings.LANGSMITH_EVAL_PROJECT,
    )


def evaluate() -> int:
    args = parse_args()
    retrieval_service = build_retrieval_service(args)

    total_precision = 0.0
    total_recall = 0.0
    total_rr = 0.0
    total_source_hit = 0
    total_phrase_coverage = 0.0

    mandatory_passed = False
    query_count = len(RAG_RETRIEVAL_EVAL_SET)

    print(f"Starting RAG retrieval evaluation for {query_count} queries (K={args.k})")
    print(f"Knowledge collection: {args.knowledge_collection}")
    print(f"Product collection  : {args.product_collection}\n")

    for idx, item in enumerate(RAG_RETRIEVAL_EVAL_SET, start=1):
        query = item["query"]
        expected_source_ids = item["expected_source_ids"]
        expected_phrases = item.get("expected_phrases", [])
        include_product_context = bool(item.get("include_product_context", True))

        results = retrieval_service.retrieve_relevant_chunks(
            query=query,
            top_k=args.k,
            include_product_context=include_product_context,
        )
        metrics = metric_bundle(results, expected_source_ids, expected_phrases, args.k)

        total_precision += metrics["precision"]
        total_recall += metrics["recall"]
        total_rr += metrics["rr"]
        total_source_hit += 1 if metrics["source_hit"] else 0
        total_phrase_coverage += metrics["phrase_coverage"]

        if query == MANDATORY_RETURN_POLICY_QUERY:
            mandatory_passed = metrics["source_hit"]

        print(f"[{idx}/{query_count}] Query: {query}")
        print(f"  Expected source ids: {expected_source_ids}")
        print(
            f"  Precision@{args.k}: {metrics['precision']:.4f} | "
            f"Recall@{args.k}: {metrics['recall']:.4f} | "
            f"RR: {metrics['rr']:.4f} | "
            f"Source-hit: {metrics['source_hit']} | "
            f"Phrase coverage: {metrics['phrase_coverage']:.4f}"
        )
        print(f"  Retrieved source ids: {metrics['source_ids']}")
        print()

    avg_precision = total_precision / query_count
    avg_recall = total_recall / query_count
    mrr = total_rr / query_count
    source_hit_at_k = total_source_hit / query_count
    avg_phrase_coverage = total_phrase_coverage / query_count

    print("=" * 64)
    print("RAG RETRIEVAL EVALUATION SUMMARY")
    print("=" * 64)
    print(f"Queries evaluated            : {query_count}")
    print(f"Mean Reciprocal Rank (MRR)   : {mrr:.4f}")
    print(f"Average Precision@{args.k}   : {avg_precision:.4f}")
    print(f"Average Recall@{args.k}      : {avg_recall:.4f}")
    print(f"Average Source-hit@{args.k}  : {source_hit_at_k:.4f}")
    print(f"Average Phrase Coverage      : {avg_phrase_coverage:.4f}")
    print(f"Mandatory query passed       : {mandatory_passed}")
    print("=" * 64)

    if args.strict and not mandatory_passed:
        print("Strict mode failed: mandatory Return Policy retrieval assertion did not pass.")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(evaluate())
