import re
from decimal import Decimal
from bson import Decimal128, ObjectId
from pymongo import MongoClient, ASCENDING, DESCENDING, ReturnDocument
from pymongo.errors import DuplicateKeyError, BulkWriteError
from pymongo.operations import UpdateOne
from django.conf import settings
from inventory.ports.product_repository import ProductRepository
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
        self._collection.create_index(
            [('category', ASCENDING)],
            name='category_filter',
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

    def add_many(self, products: list[dict]) -> tuple[list[dict], list[tuple[int, str]]]:
        if not products:
            return [], []
        docs = []
        for p in products:
            doc = dict(p)
            if 'price' in doc:
                doc['price'] = Decimal128(Decimal(str(doc['price'])))
            if not doc.get('barcode'):
                doc.pop('barcode', None)
            docs.append(doc)

        errors: list[tuple[int, str]] = []
        try:
            self._collection.insert_many(docs, ordered=False)
        except BulkWriteError as exc:
            for we in exc.details.get('writeErrors', []):
                errors.append((we['index'], 'Product with this barcode already exists'))
        error_indices = {i for i, _ in errors}
        saved = [self.to_dict(doc) for i, doc in enumerate(docs) if i not in error_indices]
        return saved, errors
    
    # Get product by ID
    def get_by_id(self, product_id: str):
        doc = self._collection.find_one({
            '_id': ObjectId(product_id),
            'is_deleted': {'$ne': True},
        })
        if doc is None:
            return None
        return self.to_dict(doc)

    def get_many_by_ids(self, product_ids: list[str]) -> dict[str, dict]:
        if not product_ids:
            return {}
        object_ids = [ObjectId(pid) for pid in product_ids]
        docs = self._collection.find({
            '_id': {'$in': object_ids},
            'is_deleted': {'$ne': True},
        })
        return {str(doc['_id']): self.to_dict(doc) for doc in docs}
    
    # List products with pagination
    def list_paginated(self, page_size: int, after=None, categories=None, search=None) -> dict:
        query: dict = {'is_deleted': {'$ne': True}}
        if after is not None:
            query['_id'] = {'$lt': ObjectId(after)}
        if categories:
            query['category'] = {'$in': categories} if len(categories) > 1 else categories[0]
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

    def update_many(self, updates: list[tuple[str, dict]]) -> tuple[list[dict], list[tuple[int, str]]]:
        if not updates:
            return [], []

        bulk_ops = []
        for product_id, changes in updates:
            set_fields: dict = {}
            unset_fields: dict = {}
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
                continue

            bulk_ops.append(UpdateOne(
                {'_id': ObjectId(product_id), 'is_deleted': {'$ne': True}},
                update_op,
            ))

        errors: list[tuple[int, str]] = []
        failed_indices: set[int] = set()

        try:
            self._collection.bulk_write(bulk_ops, ordered=False)
        except BulkWriteError as exc:
            for we in exc.details.get('writeErrors', []):
                idx = we['index']
                failed_indices.add(idx)
                # code 11000 = duplicate key
                if we.get('code') == 11000:
                    errors.append((idx, 'Product with this barcode already exists'))
                else:
                    errors.append((idx, we.get('errmsg', 'Update failed')))
        successful_ids = [
            ObjectId(product_id)
            for i, (product_id, _) in enumerate(updates)
            if i not in failed_indices
        ]
        fetched = {
            str(doc['_id']): self.to_dict(doc)
            for doc in self._collection.find({'_id': {'$in': successful_ids}})
        }
        updated = []
        for i, (product_id, _) in enumerate(updates):
            if i in failed_indices:
                continue
            if product_id in fetched:
                updated.append(fetched[product_id])
            else:
                errors.append((i, 'Product not found'))

        return updated, errors
    
    # Delete product from MongoDB document
    def delete(self, product_id: str) -> None:
        self._collection.update_one(
            {'_id': ObjectId(product_id)},
            {'$set': {'is_deleted': True}, '$unset': {'barcode': ''}},
        )

    def delete_many(self, product_ids: list[str]) -> int:
        if not product_ids:
            return 0
        object_ids = [ObjectId(pid) for pid in product_ids]
        result = self._collection.update_many(
            {'_id': {'$in': object_ids}, 'is_deleted': {'$ne': True}},
            {'$set': {'is_deleted': True}, '$unset': {'barcode': ''}},
        )
        return result.matched_count

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