import argparse
import os
import re
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), "../../"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "django_app.settings")

import django

django.setup()

from django.conf import settings

from inventory.adapters.e5_base_instruct import embedding_provider
from inventory.adapters.google_genai_provider import get_google_genai_provider
from inventory.adapters.langchain_google_genai_adapter import LangChainGoogleGenAIAdapter
from inventory.adapters.langsmith_tracer import LangSmithTracer
from inventory.adapters.product_repository import product_repository
from inventory.adapters.python_logger import PythonProductLogger
from inventory.adapters.qdrant_repository import QdrantVectorRepository
from inventory.services.rag_qa_service import RAGQAService
from inventory.services.rag_retrieval_service import RAGRetrievalService
from inventory.tests.rag_qa_eval_set import RAG_QA_EVAL_SET


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate end-to-end RAG QA quality")
    parser.add_argument("--k", type=int, default=settings.RAG_RETRIEVAL_TOP_K, help="Top K retrieval context size")
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
        help="Fail with non-zero exit code when QA acceptance checks fail",
    )
    return parser.parse_args()


def tokenize(text: str) -> set[str]:
    tokens = re.findall(r"[a-zA-Z0-9]{4,}", (text or "").lower())
    return set(tokens)


def keyword_coverage(answer: str, expected_keywords: list[str]) -> float:
    if not expected_keywords:
        return 1.0
    answer_lower = (answer or "").lower()
    hits = sum(1 for keyword in expected_keywords if keyword.lower() in answer_lower)
    return hits / len(expected_keywords)


def faithfulness_proxy(answer: str, sources: list[dict]) -> float:
    answer_tokens = tokenize(answer)
    if not answer_tokens:
        return 0.0

    context_text = "\n".join(str(s.get("content", "")) for s in sources)
    context_tokens = tokenize(context_text)
    if not context_tokens:
        return 0.0

    overlap = answer_tokens.intersection(context_tokens)
    return len(overlap) / len(answer_tokens)


def citation_correctness(sources: list[dict], expected_source_ids: list[str]) -> float:
    if not sources or not expected_source_ids:
        return 0.0
    source_ids = [str(s.get("source_id", "")) for s in sources]
    hits = sum(1 for source_id in source_ids if source_id in expected_source_ids)
    return hits / len(sources)


def source_hit(sources: list[dict], expected_source_ids: list[str]) -> bool:
    source_ids = {str(s.get("source_id", "")) for s in sources}
    return any(source_id in source_ids for source_id in expected_source_ids)


def strict_assertion_failures(query: str, sh: bool, kc: float, min_keyword: float) -> list[str]:
    failures: list[str] = []
    if not sh:
        failures.append(f"Query '{query}' failed source-hit assertion")
    if kc < min_keyword:
        failures.append(
            f"Query '{query}' failed keyword coverage assertion ({kc:.4f} < {min_keyword:.4f})"
        )
    return failures


def build_qa_service(args: argparse.Namespace) -> RAGQAService:
    logger = PythonProductLogger("inventory.tests.evaluate_rag_qa")
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

    retrieval_service = RAGRetrievalService(
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

    llm_adapter = LangChainGoogleGenAIAdapter(
        ai_provider=get_google_genai_provider(),
        logger=logger,
    )

    return RAGQAService(
        retriever=retrieval_service,
        llm_adapter=llm_adapter,
        logger=logger,
        tracer=tracer,
        trace_project=settings.LANGSMITH_EVAL_PROJECT,
    )


def evaluate() -> int:
    args = parse_args()
    qa_service = build_qa_service(args)

    total_keyword_coverage = 0.0
    total_faithfulness = 0.0
    total_citation_correctness = 0.0
    total_source_hit = 0
    query_count = len(RAG_QA_EVAL_SET)

    strict_failures: list[str] = []

    print(f"Starting RAG QA evaluation for {query_count} queries (K={args.k})")
    print(f"Knowledge collection: {args.knowledge_collection}")
    print(f"Product collection  : {args.product_collection}\n")

    for idx, item in enumerate(RAG_QA_EVAL_SET, start=1):
        query = item["query"]
        expected_source_ids = item.get("expected_source_ids", [])
        expected_keywords = item.get("expected_keywords", [])
        min_keyword = float(item.get("min_keyword_coverage", 0.0))

        response = qa_service.ask_expert(
            {
                "query": query,
                "top_k": args.k,
                "include_product_context": bool(item.get("include_product_context", True)),
            }
        )

        answer = str(response.get("answer", ""))
        sources = response.get("sources", []) or []

        kc = keyword_coverage(answer, expected_keywords)
        fp = faithfulness_proxy(answer, sources)
        cc = citation_correctness(sources, expected_source_ids)
        sh = source_hit(sources, expected_source_ids)

        total_keyword_coverage += kc
        total_faithfulness += fp
        total_citation_correctness += cc
        total_source_hit += 1 if sh else 0

        if args.strict:
            strict_failures.extend(strict_assertion_failures(query, sh, kc, min_keyword))

        print(f"[{idx}/{query_count}] Query: {query}")
        print(f"  Source-hit: {sh}")
        print(f"  Keyword coverage      : {kc:.4f}")
        print(f"  Citation correctness  : {cc:.4f}")
        print(f"  Faithfulness proxy    : {fp:.4f}")
        print(f"  Returned sources      : {[s.get('source_id', '') for s in sources]}")
        print()

    avg_keyword_coverage = total_keyword_coverage / query_count
    avg_faithfulness = total_faithfulness / query_count
    avg_citation_correctness = total_citation_correctness / query_count
    source_hit_rate = total_source_hit / query_count

    print("=" * 64)
    print("RAG QA EVALUATION SUMMARY")
    print("=" * 64)
    print(f"Queries evaluated              : {query_count}")
    print(f"Average keyword coverage       : {avg_keyword_coverage:.4f}")
    print(f"Average citation correctness   : {avg_citation_correctness:.4f}")
    print(f"Average faithfulness proxy     : {avg_faithfulness:.4f}")
    print(f"Average source-hit rate        : {source_hit_rate:.4f}")
    print("=" * 64)

    if args.strict and strict_failures:
        print("Strict mode failed:")
        for failure in strict_failures:
            print(f"  - {failure}")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(evaluate())
