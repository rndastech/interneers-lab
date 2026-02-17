from datetime import datetime
from inventory.domain.product import Product
from inventory.domain.validators import (
    validate_required_fields,
    validate_price,
    validate_quantity,
    validate_product_id,
    validate_minimum_stock_level,
    validate_pagination,
)
from inventory.domain.exceptions import NotFoundError, DuplicateError, ValidationError
from inventory.ports.repository import ProductRepository

ALLOWED_UPDATE_FIELDS = [
    'name', 'description', 'barcode', 'category', 'brand',
    'price', 'quantity', 'minimum_stock_level',
]

class ProductService:

    def __init__(self, repository: ProductRepository):
        self._repo = repository

    def validate_barcode_uniqueness(self, barcode, exclude_id=None):
        if barcode and self._repo.barcode_exists(barcode, exclude_id=exclude_id):
            raise DuplicateError('Product with this barcode already exists')

    def create_product(self, data: dict) -> dict:
        validate_required_fields(data, ['name', 'price', 'quantity'])
        price = validate_price(data['price'])
        quantity = validate_quantity(data.get('quantity'))
        if 'barcode' in data:
            self.validate_barcode_uniqueness(data['barcode'])
        minimum_stock_level = 0
        if 'minimum_stock_level' in data:
            minimum_stock_level = validate_minimum_stock_level(data['minimum_stock_level'])
        
        now = datetime.now().isoformat()
        product = Product(
            id=self._repo.next_id(),
            name=data['name'],
            description=data.get('description', ''),
            barcode=data.get('barcode', ''),
            category=data.get('category', ''),
            brand=data.get('brand', ''),
            price=str(price),
            quantity=quantity,
            minimum_stock_level=minimum_stock_level,
            created_at=now,
            updated_at=now,
        )
        return self._repo.add(product.to_dict())

    def get_product(self, raw_id) -> dict:
        product_id = validate_product_id(raw_id)
        product = self._repo.get_by_id(product_id)
        if product is None:
            raise NotFoundError()
        return product

    def list_products(self, category=None, search=None, raw_page=None, raw_page_size=None) -> dict:
        page, page_size = validate_pagination(raw_page, raw_page_size)
        products = self._repo.list_all()
        if category:
            products = [p for p in products if p['category'] == category]
        if search:
            search_lower = search.lower()
            products = [
                p for p in products
                if search_lower in p['name'].lower()
                or search_lower in p.get('barcode', '').lower()
                or search_lower in p.get('description', '').lower()
            ]
        total_count = len(products)
        start_index = (page - 1) * page_size
        end_index = start_index + page_size
        paginated_products = products[start_index:end_index]
        return {
            'count': total_count,
            'page': page,
            'page_size': page_size,
            'total_pages': (total_count + page_size - 1) // page_size,
            'results': paginated_products
        }

    def update_product(self, raw_id, data: dict) -> dict:
        product_id = validate_product_id(raw_id)
        product = self._repo.get_by_id(product_id)
        if product is None:
            raise NotFoundError()
        if 'barcode' in data and data['barcode'] != product.get('barcode'):
            self.validate_barcode_uniqueness(data['barcode'], exclude_id=product_id)
        if 'price' in data:
            price = validate_price(data['price'])
            data['price'] = str(price)
        if 'quantity' in data:
            data['quantity'] = validate_quantity(data['quantity'])
        if 'minimum_stock_level' in data:
            data['minimum_stock_level'] = validate_minimum_stock_level(data['minimum_stock_level'])

        for field in ALLOWED_UPDATE_FIELDS:
            if field in data:
                product[field] = data[field]

        product['updated_at'] = datetime.now().isoformat()
        return self._repo.update(product_id, product)

    def delete_product(self, raw_id) -> None:
        product_id = validate_product_id(raw_id)
        product = self._repo.get_by_id(product_id)
        if product is None:
            raise NotFoundError()
        self._repo.delete(product_id)
