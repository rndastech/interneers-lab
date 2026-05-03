from __future__ import annotations

from contextlib import nullcontext
from typing import Any

from inventory.adapters.langchain_google_genai_adapter import LangChainGoogleGenAIAdapter
from inventory.adapters.langsmith_tracer import LangSmithTracer
from inventory.domain.exceptions import ValidationError
from inventory.domain.sys_prompts import ASK_EXPERT_SYSTEM_INSTRUCTION
from inventory.domain.schemas import (
    AskExpertResponseSchema,
    RetrievedChunkSchema,
    validate_ask_expert_request,
    validate_ask_expert_response,
)
from inventory.ports.logger import ProductLogger
from inventory.ports.rag_retriever import RAGRetriever


class RAGQAService:

    def __init__(
        self,
        retriever: RAGRetriever,
        llm_adapter: LangChainGoogleGenAIAdapter,
        logger: ProductLogger,
        tracer: LangSmithTracer | None = None,
        trace_project: str | None = None,
    ) -> None:
        self._retriever = retriever
        self._llm_adapter = llm_adapter
        self._logger = logger
        self._tracer = tracer
        self._trace_project = trace_project

    def ask_expert(self, request_data: dict[str, Any]) -> dict[str, Any]:
        validated_request = validate_ask_expert_request(request_data)

        with self._trace(
            name="rag.ask_expert",
            metadata={
                "component": "RAGQAService",
                "top_k": validated_request.top_k,
                "category": validated_request.category,
                "include_product_context": validated_request.include_product_context,
            },
            inputs={
                "query": validated_request.query,
                "top_k": validated_request.top_k,
                "category": validated_request.category,
                "include_product_context": validated_request.include_product_context,
            },
        ):
            sources = self._retriever.retrieve_relevant_chunks(
                query=validated_request.query,
                top_k=validated_request.top_k,
                category=validated_request.category,
                include_product_context=validated_request.include_product_context,
            )

            if not sources:
                response = AskExpertResponseSchema(
                    answer=(
                        "I could not find relevant source chunks for this question yet. "
                        "Please ingest knowledge docs and try again."
                    ),
                    sources=[],
                    token_usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                    metadata={"grounded": False, "reason": "no_retrieval_results"},
                )
                return response.model_dump()

            context = self._build_context(sources)
            answer_text, token_usage = self._llm_adapter.generate_grounded_answer(
                question=validated_request.query,
                context=context,
                system_instruction=ASK_EXPERT_SYSTEM_INSTRUCTION,
            )

            response_data = {
                "answer": answer_text,
                "sources": [chunk.model_dump() for chunk in sources],
                "token_usage": token_usage,
                "metadata": {
                    "grounded": True,
                    "top_k": validated_request.top_k,
                    "source_count": len(sources),
                    "include_product_context": validated_request.include_product_context,
                    "category": validated_request.category,
                },
            }
            validated_response = validate_ask_expert_response(response_data)

        self._logger.info(
            "ask_expert completed",
            query=validated_request.query,
            top_k=validated_request.top_k,
            source_count=len(sources),
            total_tokens=validated_response.token_usage.get("total_tokens", 0)
            if validated_response.token_usage
            else 0,
        )
        return validated_response.model_dump()

    @staticmethod
    def _build_context(chunks: list[RetrievedChunkSchema]) -> str:
        sections: list[str] = []
        for idx, chunk in enumerate(chunks, start=1):
            sections.append(
                f"[Source {idx}]\n"
                f"Source Name: {chunk.source_name}\n"
                f"Source ID: {chunk.source_id}\n"
                f"Chunk ID: {chunk.chunk_id}\n"
                f"Score: {chunk.score:.4f}\n"
                f"Content: {chunk.content}"
            )
        context = "\n\n".join(sections).strip()
        if not context:
            raise ValidationError("Unable to build context from retrieved chunks")
        return context

    def _trace(self, *, name: str, metadata: dict[str, Any], inputs: dict[str, Any]):
        if not self._tracer:
            return nullcontext()
        return self._tracer.trace(
            name=name,
            project_name=self._trace_project,
            metadata=metadata,
            inputs=inputs,
        )
