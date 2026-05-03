from __future__ import annotations

import re
import importlib
from pathlib import Path
from typing import Any

from inventory.domain.exceptions import ValidationError
from inventory.domain.vector import VectorDocument
from inventory.ports.embedding_provider import EmbeddingProvider
from inventory.ports.logger import ProductLogger
from inventory.ports.vector_repository import VectorRepository


class RAGIngestionService:

    def __init__(
        self,
        vector_repository: VectorRepository,
        embedding_provider: EmbeddingProvider,
        logger: ProductLogger,
        *,
        knowledge_dir: str,
        chunk_size: int,
        chunk_overlap: int,
    ) -> None:
        self._vector_repo = vector_repository
        self._embedding_provider = embedding_provider
        self._logger = logger
        self._knowledge_dir = Path(knowledge_dir)
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap
        self._validate_chunking_config()

    def ingest(self, *, clear_existing: bool = False) -> dict[str, Any]:
        self._logger.info(
            "RAG knowledge ingestion started",
            knowledge_dir=str(self._knowledge_dir),
            clear_existing=clear_existing,
            chunk_size=self._chunk_size,
            chunk_overlap=self._chunk_overlap,
        )

        source_docs = self._load_source_documents()
        vector_docs = self._build_vector_documents(source_docs)

        if clear_existing:
            cleared = self._vector_repo.clear()
            if not cleared:
                raise ValidationError("Failed to clear existing knowledge collection before reseed")
            self._logger.info("Knowledge collection cleared before reseed")

        if not vector_docs:
            return {
                "source_count": len(source_docs),
                "chunk_count": 0,
                "upserted_count": 0,
                "failed_count": 0,
                "failed_ids": [],
                "source_chunk_counts": {},
            }

        upserted_ids, failed_ids = self._vector_repo.upsert_batch(vector_docs)
        source_chunk_counts = self._source_chunk_counts(vector_docs)

        self._logger.info(
            "RAG knowledge ingestion finished",
            source_count=len(source_docs),
            chunk_count=len(vector_docs),
            upserted_count=len(upserted_ids),
            failed_count=len(failed_ids),
        )

        return {
            "source_count": len(source_docs),
            "chunk_count": len(vector_docs),
            "upserted_count": len(upserted_ids),
            "failed_count": len(failed_ids),
            "failed_ids": failed_ids,
            "source_chunk_counts": source_chunk_counts,
        }

    def _validate_chunking_config(self) -> None:
        if self._chunk_size <= 0:
            raise ValidationError("RAG chunk_size must be > 0")
        if self._chunk_overlap < 0:
            raise ValidationError("RAG chunk_overlap must be >= 0")
        if self._chunk_overlap >= self._chunk_size:
            raise ValidationError("RAG chunk_overlap must be smaller than chunk_size")

    def _load_source_documents(self) -> list[dict[str, str]]:
        if not self._knowledge_dir.exists() or not self._knowledge_dir.is_dir():
            raise ValidationError(
                f"RAG knowledge directory does not exist or is not a directory: {self._knowledge_dir}"
            )

        files = sorted(self._knowledge_dir.glob("*.txt"))
        if not files:
            raise ValidationError(f"No .txt source documents found under: {self._knowledge_dir}")

        docs: list[dict[str, str]] = []
        for path in files:
            text = path.read_text(encoding="utf-8").strip()
            if not text:
                self._logger.warning("Skipping empty source document", file_name=path.name)
                continue
            docs.append(
                {
                    "source_id": self._source_id_from_file(path.name),
                    "source_name": path.stem.replace("_", " ").strip().title(),
                    "file_name": path.name,
                    "content": text,
                }
            )

        if not docs:
            raise ValidationError("All source documents were empty after load")

        self._logger.info("Loaded source documents", source_count=len(docs))
        return docs

    def _build_vector_documents(self, source_docs: list[dict[str, str]]) -> list[VectorDocument]:
        chunk_records: list[dict[str, Any]] = []
        chunk_texts: list[str] = []

        for source in source_docs:
            chunks = self._split_text(source["content"])
            self._logger.debug(
                "Chunked source document",
                source_id=source["source_id"],
                file_name=source["file_name"],
                chunk_count=len(chunks),
            )

            for idx, chunk in enumerate(chunks):
                clean_chunk = chunk.strip()
                if not clean_chunk:
                    continue
                chunk_id = f"{source['source_id']}::chunk::{idx}"
                vector_id = f"knowledge::{chunk_id}"
                chunk_records.append(
                    {
                        "vector_id": vector_id,
                        "chunk_id": chunk_id,
                        "source_id": source["source_id"],
                        "source_name": source["source_name"],
                        "file_name": source["file_name"],
                        "chunk_index": idx,
                        "content": clean_chunk,
                    }
                )
                chunk_texts.append(clean_chunk)

        if not chunk_records:
            return []

        embeddings = self._embedding_provider.generate_embeddings(chunk_texts, text_type="passage")
        if len(embeddings) != len(chunk_records):
            raise ValidationError(
                "Embedding count mismatch during knowledge ingestion: "
                f"expected {len(chunk_records)}, got {len(embeddings)}"
            )

        vector_docs: list[VectorDocument] = []
        for record, embedding in zip(chunk_records, embeddings):
            if not embedding:
                self._logger.warning(
                    "Skipping chunk due to empty embedding",
                    vector_id=record["vector_id"],
                )
                continue
            vector_docs.append(
                VectorDocument(
                    vector_id=record["vector_id"],
                    embedding=embedding,
                    metadata={
                        "doc_type": "knowledge",
                        "source_id": record["source_id"],
                        "source_name": record["source_name"],
                        "file_name": record["file_name"],
                        "chunk_id": record["chunk_id"],
                        "chunk_index": record["chunk_index"],
                        "content": record["content"],
                    },
                )
            )

        return vector_docs

    def _split_text(self, text: str) -> list[str]:
        try:
            module = importlib.import_module("langchain_text_splitters")
            splitter_cls = getattr(module, "RecursiveCharacterTextSplitter")
        except Exception:
            try:
                module = importlib.import_module("langchain.text_splitter")
                splitter_cls = getattr(module, "RecursiveCharacterTextSplitter")
            except Exception as e:
                raise ValidationError(
                    "LangChain text splitter is unavailable. Install langchain-text-splitters."
                ) from e

        splitter = splitter_cls(
            chunk_size=self._chunk_size,
            chunk_overlap=self._chunk_overlap,
            length_function=len,
            separators=["\n\n", "\n", ". ", " ", ""],
        )
        return splitter.split_text(text)

    @staticmethod
    def _source_id_from_file(file_name: str) -> str:
        stem = Path(file_name).stem.strip().lower()
        normalized = re.sub(r"[^a-z0-9]+", "_", stem)
        return normalized.strip("_") or "knowledge_source"

    @staticmethod
    def _source_chunk_counts(vector_docs: list[VectorDocument]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for doc in vector_docs:
            source_id = str(doc.metadata.get("source_id", "unknown"))
            counts[source_id] = counts.get(source_id, 0) + 1
        return counts
