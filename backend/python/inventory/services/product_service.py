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

    def __init__(self, repository: ProductRepository, logger: ProductLogger, category_repository: Optional[CategoryRepository] = None):
        self._repo = repository
        self._logger = logger
        self._category_repo = category_repository

    def validate_category_exists(self, category: str) -> None:
        if not category or self._category_repo is None:
            return
        normalised = category.strip().lower()
        if not self._category_repo.title_exists(normalised):
            self._logger.error('Category not found', category=normalised)
            raise NotFoundError(f"Category '{normalised}' {CATEGORY_NOT_FOUND_MESSAGE.lower()}")

    def validate_barcode_uniqueness(self, barcode, exclude_id=None):
        if barcode and self._repo.barcode_exists(barcode, exclude_id=exclude_id):
            self._logger.error(
                'Duplicate barcode rejected',
                barcode=barcode,
                exclude_id=exclude_id,
            )
            raise DuplicateError('Product with this barcode already exists')

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

    def create_product(self, data: dict) -> dict:
        self._logger.debug('create_product called', incoming_fields=list(data.keys()))

        validate_required_fields(data, REQUIRED_CREATE_FIELDS)
        price = validate_price(data['price'])
        quantity = validate_quantity(data.get('quantity'))
        if 'barcode' in data:
            self.validate_barcode_uniqueness(data['barcode'])
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
        saved = self._repo.add(product.to_dict())

        self._logger.info(
            'Product created successfully',
            product_id=saved['id'],
        )
        self.low_stock_check(saved)
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
        product = self._repo.get_by_id(product_id)
        if product is None:
            self._logger.error('Product not found for update', product_id=product_id)
            raise NotFoundError(PRODUCT_NOT_FOUND_MESSAGE)

        if 'barcode' in data and data['barcode'] != product.get('barcode'):
            self.validate_barcode_uniqueness(data['barcode'], exclude_id=product_id)

        if 'category' in data and data['category']:
            data['category'] = data['category'].strip().lower()
            self.validate_category_exists(data['category'])

        if 'price' in data:
            price = validate_price(data['price'])
            data['price'] = price
        if 'quantity' in data:
            data['quantity'] = validate_quantity(data['quantity'])
        if 'minimum_stock_level' in data:
            data['minimum_stock_level'] = validate_minimum_stock_level(data['minimum_stock_level'])

        updated_fields = [field for field in ALLOWED_UPDATE_FIELDS if field in data]
        self._logger.debug(
            'Applying field updates',
            product_id=product_id,
            updated_fields=updated_fields,
        )
        changes = {field: data[field] for field in ALLOWED_UPDATE_FIELDS if field in data}
        changes['updated_at'] = datetime.now().isoformat()
        saved = self._repo.update(product_id, changes)
        if saved is None:
            self._logger.error('Concurrent delete', product_id=product_id)
            raise NotFoundError(PRODUCT_NOT_FOUND_MESSAGE)
        self._logger.info(
            'Product updated successfully',
            product_id=product_id,
            updated_fields=updated_fields,
        )
        self.low_stock_check(saved)
        return saved

    def delete_product(self, raw_id) -> None:
        self._logger.debug('delete_product called', raw_id=raw_id)

        product_id = validate_product_id(raw_id)
        product = self._repo.get_by_id(product_id)
        if product is None:
            self._logger.error('Product not found for deletion', product_id=product_id)
            raise NotFoundError(PRODUCT_NOT_FOUND_MESSAGE)

        self._repo.delete(product_id)
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
        created = []
        errors = []
        for row_index, raw_row in enumerate(rows, start=1):
            row = {k: (v.strip() if isinstance(v, str) else v) for k, v in raw_row.items()}
            row = {k: v for k, v in row.items() if k in CSV_ALLOWED_COLUMNS}

            self._logger.debug(
                'Processing CSV create row',
                row_number=row_index,
                row_keys=list(row.keys()),
            )

            try:
                product = self.create_product(row)
                created.append(product)
                self._logger.info(
                    'CSV row created successfully',
                    row_number=row_index,
                    product_id=product['id'],
                )
            except (ValidationError, NotFoundError, DuplicateError) as exc:
                self._logger.warning(
                    'CSV create row skipped due to error',
                    row_number=row_index,
                    error=exc.message,
                )
                errors.append({'row': row_index, 'data': raw_row, 'error': exc.message})

        self._logger.info(
            'create_product_csv complete',
            total_rows=len(rows),
            created_count=len(created),
            error_count=len(errors),
        )
        return {'created': created, 'errors': errors}

    def update_product_csv(self, file_obj) -> dict:
        self._logger.debug('update_product_csv called')

        rows = self.parse_csv(file_obj)
        validate_csv_update(rows)

        self._logger.info('update_product_csv parsed', total_rows=len(rows))

        updated = []
        errors = []

        for row_index, raw_row in enumerate(rows, start=1):
            row = {k: (v.strip() if isinstance(v, str) else v) for k, v in raw_row.items()}
            row = {k: v for k, v in row.items() if k in CSV_UPDATE_ALLOWED_COLUMNS}

            self._logger.debug(
                'Processing CSV update row',
                row_number=row_index,
                row_keys=list(row.keys()),
            )

            try:
                raw_id = row.pop('id', None)
                if not row:
                    raise ValidationError('Row must contain at least one field to update besides id')
                product = self.update_product(raw_id, row)
                updated.append(product)
                self._logger.info(
                    'CSV row updated successfully',
                    row_number=row_index,
                    product_id=product['id'],
                )
            except (ValidationError, NotFoundError, DuplicateError) as exc:
                self._logger.warning(
                    'CSV update row skipped due to error',
                    row_number=row_index,
                    error=exc.message,
                )
                errors.append({'row': row_index, 'data': raw_row, 'error': exc.message})

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

        deleted = []
        errors = []

        for row_index, raw_row in enumerate(rows, start=1):
            row = {k: (v.strip() if isinstance(v, str) else v) for k, v in raw_row.items()}
            raw_id = row.get('id')

            self._logger.debug(
                'Processing CSV delete row',
                row_number=row_index,
                raw_id=raw_id,
            )

            try:
                self.delete_product(raw_id)
                deleted.append(str(raw_id))
                self._logger.info(
                    'CSV row deleted successfully',
                    row_number=row_index,
                    product_id=raw_id,
                )
            except (ValidationError, NotFoundError) as exc:
                self._logger.warning(
                    'CSV delete row skipped due to error',
                    row_number=row_index,
                    error=exc.message,
                )
                errors.append({'row': row_index, 'data': raw_row, 'error': exc.message})

        self._logger.info(
            'delete_product_csv complete',
            total_rows=len(rows),
            deleted_count=len(deleted),
            error_count=len(errors),
        )
        return {'deleted': deleted, 'errors': errors}
