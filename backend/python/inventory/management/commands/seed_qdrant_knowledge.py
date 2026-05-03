from django.conf import settings
from django.core.management.base import BaseCommand

from inventory.adapters.e5_base_instruct import embedding_provider
from inventory.adapters.python_logger import PythonProductLogger
from inventory.adapters.qdrant_repository import QdrantVectorRepository
from inventory.domain.exceptions import ValidationError
from inventory.services.rag_ingestion_service import RAGIngestionService


class Command(BaseCommand):
    help = "Seed chunked knowledge documents into the dedicated Qdrant RAG collection."

    def add_arguments(self, parser):
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Clear the knowledge collection before reseeding.",
        )
        parser.add_argument(
            "--knowledge-dir",
            type=str,
            default=settings.RAG_KNOWLEDGE_DIR,
            help="Directory containing .txt knowledge source files.",
        )
        parser.add_argument(
            "--chunk-size",
            type=int,
            default=settings.RAG_CHUNK_SIZE,
            help="Chunk size for the text splitter.",
        )
        parser.add_argument(
            "--chunk-overlap",
            type=int,
            default=settings.RAG_CHUNK_OVERLAP,
            help="Chunk overlap for the text splitter.",
        )

    def handle(self, *args, **options):
        logger = PythonProductLogger("inventory.rag.ingestion")

        self.stdout.write(self.style.SUCCESS("Starting knowledge ingestion into Qdrant..."))
        self.stdout.write(f"Collection: {settings.RAG_QDRANT_COLLECTION_NAME}")
        self.stdout.write(f"Knowledge dir: {options['knowledge_dir']}")
        self.stdout.write(f"Chunk size / overlap: {options['chunk_size']} / {options['chunk_overlap']}")
        self.stdout.write(f"Clear before seed: {bool(options['clear'])}")

        vector_repo = QdrantVectorRepository(
            url=settings.QDRANT_URL,
            collection_name=settings.RAG_QDRANT_COLLECTION_NAME,
            vector_size=settings.QDRANT_VECTOR_SIZE,
            api_key=settings.QDRANT_API_KEY,
        )

        ingestion_service = RAGIngestionService(
            vector_repository=vector_repo,
            embedding_provider=embedding_provider,
            logger=logger,
            knowledge_dir=options["knowledge_dir"],
            chunk_size=options["chunk_size"],
            chunk_overlap=options["chunk_overlap"],
        )

        try:
            summary = ingestion_service.ingest(clear_existing=bool(options["clear"]))
        except ValidationError as e:
            self.stderr.write(self.style.ERROR(f"Validation error: {e.message}"))
            return
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Unexpected ingestion failure: {str(e)}"))
            raise

        self.stdout.write(self.style.SUCCESS("Knowledge ingestion complete."))
        self.stdout.write(f"Sources processed: {summary['source_count']}")
        self.stdout.write(f"Chunks built: {summary['chunk_count']}")
        self.stdout.write(f"Chunks upserted: {summary['upserted_count']}")
        self.stdout.write(f"Chunks failed: {summary['failed_count']}")

        if summary["source_chunk_counts"]:
            self.stdout.write("Per-source chunk counts:")
            for source_id, count in sorted(summary["source_chunk_counts"].items()):
                self.stdout.write(f"  - {source_id}: {count}")

        if summary["failed_ids"]:
            self.stdout.write(self.style.WARNING("Failed vector ids:"))
            for vector_id in summary["failed_ids"]:
                self.stdout.write(f"  - {vector_id}")
