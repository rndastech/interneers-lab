from datetime import datetime
from typing import Optional
import csv
import codecs
from inventory.domain.product import Product
from inventory.domain.validators import (
    validate_required_fields,
    validate_price,
    validate_quantity,
    validate_product_id,
    validate_minimum_stock_level,
    validate_cursor_pagination,
    validate_csv_create,
    validate_csv_update,
    validate_csv_delete,
)
from inventory.domain.exceptions import NotFoundError, DuplicateError, ValidationError
from inventory.ports.product_repository import ProductRepository
from inventory.ports.category_repository import CategoryRepository
from inventory.ports.logger import ProductLogger
from inventory.ports.vector_repository import VectorRepository
from inventory.ports.embedding_provider import EmbeddingProvider
from inventory.domain.vector import VectorDocument
from inventory.domain.config import (
    REQUIRED_CREATE_FIELDS,
    ALLOWED_UPDATE_FIELDS,
    DEFAULT_MINIMUM_STOCK_LEVEL,
    DEFAULT_DESCRIPTION,
    DEFAULT_BARCODE,
    DEFAULT_CATEGORY,
    DEFAULT_BRAND,
    PRODUCT_NOT_FOUND_MESSAGE,
    CATEGORY_NOT_FOUND_MESSAGE,
    CSV_ALLOWED_COLUMNS,
    CSV_UPDATE_ALLOWED_COLUMNS,
    CSV_NO_FILE_MESSAGE,
    CSV_INVALID_FORMAT_MESSAGE,
)

class ProductService:

    def __init__(self, repository: ProductRepository, logger: ProductLogger, category_repository: Optional[CategoryRepository] = None, vector_repository: Optional[VectorRepository] = None, embedding_provider: Optional[EmbeddingProvider] = None):
        self._repo = repository
        self._logger = logger
        self._category_repo = category_repository
        self._vector_repo = vector_repository
        self._embedding_provider = embedding_provider


    def _vector_deps_available(self) -> bool:
        return bool(self._vector_repo and self._embedding_provider)

    @staticmethod
    def _build_embed_text(product: dict) -> str:
        parts = [
            product.get("name", ""),
            product.get("description", ""),
            product.get("brand", ""),
            product.get("category", ""),
        ]
        return " ".join(p.strip() for p in parts if p and p.strip())

    def _sync_vectors_batch(self, products: list[dict]) -> None:
        if not self._vector_deps_available():
            self._logger.debug("Vector sync skipped: vector dependencies not provided")
            return

        candidates = [p for p in products if self._build_embed_text(p)]
        skipped = len(products) - len(candidates)
        if skipped:
            self._logger.warning(
                "Vector sync skipped for products with no embeddable text",
                skipped_count=skipped,
            )
        if not candidates:
            return

        texts = [self._build_embed_text(p) for p in candidates]
        try:
            embeddings = self._embedding_provider.generate_embeddings(texts) if self._embedding_provider else []
            docs = [
                VectorDocument(
                    vector_id=str(p["id"]),
                    embedding=emb,
                    metadata={"category": p.get("category")},
                )
                for p, emb in zip(candidates, embeddings)
                if emb
            ]
            if docs and self._vector_repo:
                self._vector_repo.upsert_batch(docs)
                self._logger.debug(
                    "Vector batch sync successful", synced_count=len(docs)
                )
        except Exception as e:
            self._logger.error(
                "Vector batch sync failed",
                product_ids=[str(p["id"]) for p in candidates],
                error=str(e),
            )

    def _sync_vector(self, product: dict) -> None:
        self._sync_vectors_batch([product])

    def _delete_vectors_batch(self, product_ids: list[str]) -> None:
        if not self._vector_repo or not product_ids:
            return
        try:
            self._vector_repo.delete_batch(product_ids)
            self._logger.debug(
                "Vector batch delete successful", deleted_count=len(product_ids)
            )
        except Exception as e:
            self._logger.error(
                "Vector batch delete failed",
                product_ids=product_ids,
                error=str(e),
            )

    def _delete_vector(self, product_id: str) -> None:
        self._delete_vectors_batch([product_id])


    def validate_category_exists(self, category: str) -> None:
        if not category or self._category_repo is None:
            return
        normalised = category.strip().lower()
        if not self._category_repo.title_exists(normalised):
            self._logger.error('Category not found', category=normalised)
            raise NotFoundError(f"Category '{normalised}' {CATEGORY_NOT_FOUND_MESSAGE.lower()}")

    def low_stock_check(self, product: dict) -> None:
        quantity = product.get('quantity', 0)
        minimum = product.get('minimum_stock_level', 0)
        if quantity <= minimum:
            self._logger.warning(
                'Product stock is at or below minimum level',
                product_id=product.get('id'),
                quantity=quantity,
                minimum_stock_level=minimum,
            )

    def _low_stock_check_many(self, products: list[dict]) -> None:
        for product in products:
            self.low_stock_check(product)

    def build_product_doc(self, data: dict) -> dict:
        validate_required_fields(data, REQUIRED_CREATE_FIELDS)
        price = validate_price(data['price'])
        quantity = validate_quantity(data.get('quantity'))
        minimum_stock_level = DEFAULT_MINIMUM_STOCK_LEVEL
        if 'minimum_stock_level' in data:
            minimum_stock_level = validate_minimum_stock_level(data['minimum_stock_level'])

        category = data.get('category', DEFAULT_CATEGORY)
        if category:
            category = category.strip().lower()
            self.validate_category_exists(category)

        now = datetime.now().isoformat()
        product = Product(
            name=data['name'],
            description=data.get('description', DEFAULT_DESCRIPTION),
            barcode=data.get('barcode', DEFAULT_BARCODE),
            category=category,
            brand=data.get('brand', DEFAULT_BRAND),
            price=price,
            quantity=quantity,
            minimum_stock_level=minimum_stock_level,
            created_at=now,
            updated_at=now,
        )
        return product.to_dict()

    def build_update_changes(self, data: dict) -> dict:
        changes = {}
        if 'category' in data and data['category']:
            data['category'] = data['category'].strip().lower()
            self.validate_category_exists(data['category'])
        if 'price' in data:
            changes['price'] = validate_price(data['price'])
        if 'quantity' in data:
            changes['quantity'] = validate_quantity(data['quantity'])
        if 'minimum_stock_level' in data:
            changes['minimum_stock_level'] = validate_minimum_stock_level(data['minimum_stock_level'])
        for field in ALLOWED_UPDATE_FIELDS:
            if field in data and field not in changes:
                changes[field] = data[field]
        changes['updated_at'] = datetime.now().isoformat()
        return changes

    def create_product(self, data: dict) -> dict:
        self._logger.debug('create_product called', incoming_fields=list(data.keys()))
        doc = self.build_product_doc(data)
        saved = self._repo.add(doc)
        self._logger.info('Product created successfully', product_id=saved['id'])
        self.low_stock_check(saved)
        self._sync_vector(saved)
        return saved

    def get_product(self, raw_id) -> dict:
        self._logger.debug('get_product called', raw_id=raw_id)

        product_id = validate_product_id(raw_id)
        product = self._repo.get_by_id(product_id)
        if product is None:
            self._logger.error('Product not found', product_id=product_id)
            raise NotFoundError(PRODUCT_NOT_FOUND_MESSAGE)

        self._logger.info('Product retrieved', product_id=product_id)
        return product

    def get_many_by_ids(self, raw_ids: list[str]) -> dict[str, dict]:
        self._logger.debug('get_many_by_ids called', raw_count=len(raw_ids))
        if not raw_ids:
            return {}

        validated_ids = [validate_product_id(raw_id) for raw_id in raw_ids]
        unique_ids = list(dict.fromkeys(validated_ids))
        products = self._repo.get_many_by_ids(unique_ids)

        missing = [pid for pid in unique_ids if pid not in products]
        if missing:
            self._logger.warning(
                'Products not found',
                missing_count=len(missing),
                missing_ids=missing[:10],
            )

        self._logger.info(
            'Products retrieved in batch',
            requested_count=len(unique_ids),
            returned_count=len(products),
        )
        return products

    def list_products(self, categories=None, search=None, raw_page_size=None, raw_after=None) -> dict:
        self._logger.debug(
            'list_products called',
            categories=categories,
            search=search,
            raw_page_size=raw_page_size,
            raw_after=raw_after,
        )

        page_size, after = validate_cursor_pagination(raw_page_size, raw_after)
        result = self._repo.list_paginated(
            page_size=page_size,
            after=after,
            categories=categories,
            search=search,
        )

        self._logger.info(
            'Product list returned',
            page_size=page_size,
            after=after,
            returned_count=len(result['results']),
            has_next=result['next_cursor'] is not None,
        )
        return result

    def update_product(self, raw_id, data: dict) -> dict:
        self._logger.debug(
            'update_product called',
            raw_id=raw_id,
            fields_to_update=list(data.keys()),
        )

        product_id = validate_product_id(raw_id)
        changes = self.build_update_changes(data)
        self._logger.debug('Applying field updates', product_id=product_id, updated_fields=list(changes.keys()))
        saved = self._repo.update(product_id, changes)
        if saved is None:
            self._logger.error('Concurrent delete', product_id=product_id)
            raise NotFoundError(PRODUCT_NOT_FOUND_MESSAGE)
        self._logger.info(
            'Product updated successfully',
            product_id=product_id,
            updated_fields=list(changes.keys())
            )
        self.low_stock_check(saved)
        self._sync_vector(saved)
        return saved

    def delete_product(self, raw_id) -> None:
        self._logger.debug('delete_product called', raw_id=raw_id)

        product_id = validate_product_id(raw_id)
        product = self._repo.get_by_id(product_id)
        if product is None:
            self._logger.error('Product not found for deletion', product_id=product_id)
            raise NotFoundError(PRODUCT_NOT_FOUND_MESSAGE)

        self._repo.delete(product_id)
        self._delete_vector(product_id)
        self._logger.info('Product deleted', product_id=product_id)

    def parse_csv(self, file_obj) -> list[dict]:
        if file_obj is None:
            self._logger.error('No CSV file provided')
            raise ValidationError(CSV_NO_FILE_MESSAGE)
        try:
            reader = csv.DictReader(codecs.iterdecode(file_obj, 'utf-8-sig'))
            rows = list(reader)
        except (UnicodeDecodeError, csv.Error) as exc:
            self._logger.error('CSV file could not be parsed', error=str(exc))
            raise ValidationError(f'{CSV_INVALID_FORMAT_MESSAGE}: {exc}')
        return rows

    def create_product_csv(self, file_obj) -> dict:
        self._logger.debug('create_product_csv called')
        rows = self.parse_csv(file_obj)
        validate_csv_create(rows)
        self._logger.info('create_product_csv parsed', total_rows=len(rows))
        valid_docs: list[dict] = [] 
        valid_row_indices: list[int] = []
        errors: list[dict] = []

        for row_index, raw_row in enumerate(rows, start=1):
            row = {k: (v.strip() if isinstance(v, str) else v) for k, v in raw_row.items()}
            row = {k: v for k, v in row.items() if k in CSV_ALLOWED_COLUMNS}
            self._logger.debug('Validating CSV create row', row_number=row_index, row_keys=list(row.keys()))
            try:
                doc = self.build_product_doc(row)
                valid_docs.append(doc)
                valid_row_indices.append(row_index)
            except (ValidationError, NotFoundError, DuplicateError) as exc:
                self._logger.warning('CSV create row invalid', row_number=row_index, error=exc.message)
                errors.append({'row': row_index, 'data': raw_row, 'error': exc.message})

        saved, repo_errors = self._repo.add_many(valid_docs)

        for doc_index, message in repo_errors:
            original_row = valid_row_indices[doc_index]
            self._logger.warning('CSV create row rejected by DB', row_number=original_row, error=message)
            errors.append({'row': original_row, 'data': rows[original_row - 1], 'error': message})
        self._low_stock_check_many(saved)
        self._sync_vectors_batch(saved)

        for product in saved:
            self._logger.info('CSV row created successfully', product_id=product['id'])

        self._logger.info(
            'create_product_csv complete',
            total_rows=len(rows),
            created_count=len(saved),
            error_count=len(errors),
        )
        return {'created': saved, 'errors': errors}

    def update_product_csv(self, file_obj) -> dict:
        self._logger.debug('update_product_csv called')

        rows = self.parse_csv(file_obj)
        validate_csv_update(rows)

        self._logger.info('update_product_csv parsed', total_rows=len(rows))

        valid_updates: list[tuple[str, dict]] = []
        valid_row_indices: list[int] = []
        errors: list[dict] = []

        for row_index, raw_row in enumerate(rows, start=1):
            row = {k: (v.strip() if isinstance(v, str) else v) for k, v in raw_row.items()}
            row = {k: v for k, v in row.items() if k in CSV_UPDATE_ALLOWED_COLUMNS}
            self._logger.debug('Validating CSV update row', row_number=row_index, row_keys=list(row.keys()))
            try:
                raw_id = row.pop('id', None)
                product_id = validate_product_id(raw_id)
                if not row:
                    raise ValidationError('Row must contain at least one field to update besides id')
                changes = self.build_update_changes(row)
                valid_updates.append((product_id, changes))
                valid_row_indices.append(row_index)
            except (ValidationError, NotFoundError, DuplicateError) as exc:
                self._logger.warning('CSV update row invalid', row_number=row_index, error=exc.message)
                errors.append({'row': row_index, 'data': raw_row, 'error': exc.message})

        updated, repo_errors = self._repo.update_many(valid_updates)

        for doc_index, message in repo_errors:
            original_row = valid_row_indices[doc_index]
            self._logger.warning('CSV update row rejected by DB', row_number=original_row, error=message)
            errors.append({'row': original_row, 'data': rows[original_row - 1], 'error': message})
        self._low_stock_check_many(updated)
        self._sync_vectors_batch(updated)

        for product in updated:
            self._logger.info('CSV row updated successfully', product_id=product['id'])

        self._logger.info(
            'update_product_csv complete',
            total_rows=len(rows),
            updated_count=len(updated),
            error_count=len(errors),
        )
        return {'updated': updated, 'errors': errors}

    def delete_product_csv(self, file_obj) -> dict:
        self._logger.debug('delete_product_csv called')

        rows = self.parse_csv(file_obj)
        validate_csv_delete(rows)

        self._logger.info('delete_product_csv parsed', total_rows=len(rows))

        candidate_ids: list[str] = []
        candidate_row_indices: list[int] = []
        errors: list[dict] = []

        for row_index, raw_row in enumerate(rows, start=1):
            row = {k: (v.strip() if isinstance(v, str) else v) for k, v in raw_row.items()}
            raw_id = row.get('id')
            self._logger.debug('Validating CSV delete row', row_number=row_index, raw_id=raw_id)
            try:
                product_id = validate_product_id(raw_id)
                candidate_ids.append(product_id)
                candidate_row_indices.append(row_index)
            except ValidationError as exc:
                self._logger.warning('CSV delete row invalid', row_number=row_index, error=exc.message)
                errors.append({'row': row_index, 'data': raw_row, 'error': exc.message})

        existing = self._repo.get_many_by_ids(candidate_ids)

        ids_to_delete: list[str] = []
        for pid, row_index in zip(candidate_ids, candidate_row_indices):
            if pid in existing:
                ids_to_delete.append(pid)
            else:
                raw_row = rows[row_index - 1]
                self._logger.warning('CSV delete row not found', row_number=row_index, product_id=pid)
                errors.append({'row': row_index, 'data': raw_row, 'error': PRODUCT_NOT_FOUND_MESSAGE})
        self._repo.delete_many(ids_to_delete)
        self._delete_vectors_batch(ids_to_delete)

        for pid in ids_to_delete:
            self._logger.info('CSV row deleted successfully', product_id=pid)

        self._logger.info(
            'delete_product_csv complete',
            total_rows=len(rows),
            deleted_count=len(ids_to_delete),
            error_count=len(errors),
        )
        return {'deleted': ids_to_delete, 'errors': errors}