from datetime import datetime
from inventory.domain.product import Product
from inventory.domain.validators import (
    validate_required_fields,
    validate_price,
    validate_quantity,
    validate_product_id,
    validate_minimum_stock_level,
    validate_cursor_pagination,
)
from inventory.domain.exceptions import NotFoundError, DuplicateError, ValidationError
from inventory.ports.repository import ProductRepository
from inventory.ports.logger import ProductLogger
from inventory.domain.config import (
    REQUIRED_CREATE_FIELDS,
    ALLOWED_UPDATE_FIELDS,
    DEFAULT_MINIMUM_STOCK_LEVEL,
    DEFAULT_DESCRIPTION,
    DEFAULT_BARCODE,
    DEFAULT_CATEGORY,
    DEFAULT_BRAND,
)

class ProductService:

    def __init__(self, repository: ProductRepository, logger: ProductLogger):
        self._repo = repository
        self._logger = logger

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

        now = datetime.now().isoformat()
        product = Product(
            name=data['name'],
            description=data.get('description', DEFAULT_DESCRIPTION),
            barcode=data.get('barcode', DEFAULT_BARCODE),
            category=data.get('category', DEFAULT_CATEGORY),
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
            raise NotFoundError()

        self._logger.info('Product retrieved', product_id=product_id)
        return product

    def list_products(self, category=None, search=None, raw_page_size=None, raw_after=None) -> dict:
        self._logger.debug(
            'list_products called',
            category=category,
            search=search,
            raw_page_size=raw_page_size,
            raw_after=raw_after,
        )

        page_size, after = validate_cursor_pagination(raw_page_size, raw_after)
        result = self._repo.list_paginated(
            page_size=page_size,
            after=after,
            category=category,
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
            raise NotFoundError()

        if 'barcode' in data and data['barcode'] != product.get('barcode'):
            self.validate_barcode_uniqueness(data['barcode'], exclude_id=product_id)

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
            raise NotFoundError()
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
            raise NotFoundError()

        self._repo.delete(product_id)
        self._logger.info('Product deleted', product_id=product_id)
