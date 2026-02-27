import re
from decimal import Decimal
from bson import Decimal128, ObjectId
from pymongo import MongoClient, ASCENDING, DESCENDING, ReturnDocument
from pymongo.errors import DuplicateKeyError
from django.conf import settings
from inventory.ports.repository import ProductRepository
from inventory.domain.exceptions import DuplicateError


class MongoProductRepository(ProductRepository):

    def __init__(self, uri: str, db_name: str):
        self._client = MongoClient(uri)
        self._db = self._client[db_name]
        self._collection = self._db['products']
        self._collection.create_index(
            [('barcode', ASCENDING)],
            unique=True,
            sparse=True,
            name='unique_barcode',
        )

    # Add product to MongoDB document
    def add(self, product: dict) -> dict:
        doc = dict(product)
        if 'price' in doc:
            doc['price'] = Decimal128(Decimal(str(doc['price'])))
        if not doc.get('barcode'):
            doc.pop('barcode', None)
        try:
            self._collection.insert_one(doc)
        except DuplicateKeyError:
            raise DuplicateError('Product with this barcode already exists')
        return self.to_dict(doc)

    # Get product by ID
    def get_by_id(self, product_id: str):
        doc = self._collection.find_one({
            '_id': ObjectId(product_id),
            'is_deleted': {'$ne': True},
        })
        if doc is None:
            return None
        return self.to_dict(doc)

    # List products with pagination
    def list_paginated(self, page_size: int, after=None, category=None, search=None) -> dict:
        query: dict = {'is_deleted': {'$ne': True}}
        if after is not None:
            query['_id'] = {'$lt': ObjectId(after)}
        if category:
            query['category'] = category
        if search:
            escaped_search = re.escape(search.lower())
            regex_filter = {'$regex': escaped_search, '$options': 'i'}
            query['$or'] = [
                {'name': regex_filter},
                {'barcode': regex_filter},
                {'description': regex_filter},
            ]
        # Fetch one extra document to determine whether a next page exists.
        docs = list(
            self._collection
            .find(query)
            .sort('_id', DESCENDING)
            .limit(page_size + 1)
        )
        has_next = len(docs) > page_size
        docs = docs[:page_size]
        next_cursor = str(docs[-1]['_id']) if has_next and docs else None
        results = [self.to_dict(doc) for doc in docs]
        return {
            'results': results,
            'next_cursor': next_cursor,
            'page_size': page_size,
        }
    
    # Update product in MongoDB document
    def update(self, product_id: str, changes: dict) -> dict | None:
        set_fields = {}
        unset_fields = {}
        for key, value in changes.items():
            if key in ('_id', 'id'):
                continue
            if key == 'price':
                set_fields[key] = Decimal128(Decimal(str(value)))
            elif key == 'barcode' and not value:
                unset_fields[key] = ''
            else:
                set_fields[key] = value

        update_op: dict = {}
        if set_fields:
            update_op['$set'] = set_fields
        if unset_fields:
            update_op['$unset'] = unset_fields
        if not update_op:
            return self.get_by_id(product_id)

        try:
            doc = self._collection.find_one_and_update(
                {'_id': ObjectId(product_id), 'is_deleted': {'$ne': True}},
                update_op,
                return_document=ReturnDocument.AFTER,
            )
        except DuplicateKeyError:
            raise DuplicateError('Product with this barcode already exists')
        if doc is None:
            return None
        return self.to_dict(doc)

    # Delete product from MongoDB document
    def delete(self, product_id: str) -> None:
        self._collection.update_one(
            {'_id': ObjectId(product_id)},
            {'$set': {'is_deleted': True}, '$unset': {'barcode': ''}},
        )

    def barcode_exists(self, barcode: str, exclude_id=None) -> bool:
        query: dict = {
            'barcode': barcode,
            'is_deleted': {'$ne': True},
        }
        if exclude_id is not None:
            query['_id'] = {'$ne': ObjectId(exclude_id)}
        return self._collection.count_documents(query, limit=1) > 0

    @staticmethod
    def to_dict(doc: dict) -> dict:
        cleaned = dict(doc)
        if '_id' in cleaned:
            cleaned['id'] = str(cleaned.pop('_id'))
        if isinstance(cleaned.get('price'), Decimal128):
            cleaned['price'] = cleaned['price'].to_decimal()
        return cleaned


product_repository = MongoProductRepository(
    uri=settings.MONGO_URI,
    db_name=settings.MONGO_DB_NAME,
)
