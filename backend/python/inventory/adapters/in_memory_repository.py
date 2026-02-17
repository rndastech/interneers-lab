from inventory.ports.repository import ProductRepository

class InMemoryProductRepository(ProductRepository):

    def __init__(self):
        self._store = {}
        self._id_counter = 1

    def next_id(self):
        current = self._id_counter
        self._id_counter += 1
        return current

    def add(self, product):
        self._store[product['id']] = product
        return product

    def get_by_id(self, product_id):
        return self._store.get(product_id)

    def list_all(self):
        return list(self._store.values())

    def update(self, product_id, product):
        self._store[product_id] = product
        return product

    def delete(self, product_id):
        del self._store[product_id]

    def barcode_exists(self, barcode, exclude_id=None):
        for product in self._store.values():
            if product.get('barcode') == barcode and product['id'] != exclude_id:
                return True
        return False

product_repository = InMemoryProductRepository()
