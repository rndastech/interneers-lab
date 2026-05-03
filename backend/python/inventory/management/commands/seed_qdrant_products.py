from django.core.management.base import BaseCommand
from django.conf import settings
from pymongo import MongoClient
from bson import ObjectId, Decimal128
from inventory.adapters.qdrant_repository import vector_repository
from inventory.adapters.e5_base_instruct import embedding_provider
from inventory.domain.vector import VectorDocument
from inventory.adapters.python_logger import PythonProductLogger


class Command(BaseCommand):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.logger = PythonProductLogger()

    def _get_products_from_mongo(self):
        try:
            client = MongoClient(settings.MONGO_URI)
            db = client[settings.MONGO_DB_NAME]
            products_col = db['products']
            
            cursor = products_col.find({'is_deleted': {'$ne': True}})
            products = list(cursor)
            
            client.close()
            self.stdout.write(
                self.style.SUCCESS(
                    f'✓ Fetched {len(products)} products from MongoDB'
                )
            )
            return products
        except Exception as e:
            self.stderr.write(self.style.ERROR(f'Failed to fetch products from MongoDB: {str(e)}'))
            raise

    def _convert_product_to_text(self, product: dict) -> str:
        parts = []
        if 'name' in product:
            parts.append(product['name'])
        if 'description' in product:
            parts.append(product['description'])
        if 'category' in product:
            parts.append(f"Category: {product['category']}")
        if 'brand' in product:
            parts.append(f"Brand: {product['brand']}")
        
        return ' '.join(parts)

    def _create_vector_document(self, product: dict, embedding: list) -> VectorDocument:
        product_id = str(product['_id'])
        
        metadata = {
            '_id': product_id,
            'category': product.get('category', ''),
        }
        
        return VectorDocument(
            vector_id=product_id,
            embedding=embedding,
            metadata=metadata,
        )

    def _convert_decimal(self, value):
        if isinstance(value, Decimal128):
            return float(value.to_decimal())
        return value

    def handle(self, *args, **options):
        try:
            self.stdout.write(self.style.SUCCESS('\n' + '=' * 60))
            self.stdout.write(self.style.SUCCESS('Starting Qdrant Products Seed Script'))
            self.stdout.write(self.style.SUCCESS('=' * 60 + '\n'))
            products = self._get_products_from_mongo()
            if not products:
                self.stdout.write(self.style.WARNING('No products found in MongoDB'))
                return
            self.stdout.write('\n' + self.style.SUCCESS('Preparing product texts...'))
            product_texts = []
            for product in products:
                text = self._convert_product_to_text(product)
                product_texts.append(text)
            self.stdout.write(self.style.SUCCESS(f'Generating embeddings for {len(products)} products...'))
            embeddings = embedding_provider.generate_embeddings(product_texts)
            if len(embeddings) != len(products):
                raise ValueError(
                    f'Embedding count mismatch: got {len(embeddings)} embeddings '
                    f'for {len(products)} products'
                )
            self.stdout.write(self.style.SUCCESS('Upserting documents to Qdrant...'))
            vector_documents = []
            for product, embedding in zip(products, embeddings):
                doc = self._create_vector_document(product, embedding)
                vector_documents.append(doc)
            successful_ids, failed_ids = vector_repository.upsert_batch(vector_documents)
            self.stdout.write('\n' + self.style.SUCCESS('=' * 60))
            self.stdout.write(self.style.SUCCESS('Seeding Complete'))
            self.stdout.write(self.style.SUCCESS('=' * 60))
            self.stdout.write(
                self.style.SUCCESS(
                    f'\n✓ Successfully added {len(successful_ids)} products to Qdrant'
                )
            )
            if failed_ids:
                self.stdout.write(
                    self.style.WARNING(
                        f'\n⚠ Failed to add {len(failed_ids)} products'
                    )
                )
                for failed_id in failed_ids[:10]:  # Show first 10 failures
                    self.stdout.write(f'  - {failed_id}')
                if len(failed_ids) > 10:
                    self.stdout.write(f'  ... and {len(failed_ids) - 10} more')

            self.stdout.write(self.style.SUCCESS('\n' + '=' * 60 + '\n'))

        except Exception as e:
            self.stderr.write(self.style.ERROR(f'\n✗ Error during seeding: {str(e)}'))
            import traceback
            self.stderr.write(traceback.format_exc())
            raise
