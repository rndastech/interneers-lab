import re
from bson import ObjectId
from pymongo import MongoClient, ASCENDING, DESCENDING, ReturnDocument
from pymongo.errors import DuplicateKeyError
from django.conf import settings
from inventory.ports.category_repository import CategoryRepository
from inventory.domain.exceptions import DuplicateError


class MongoCategoryRepository(CategoryRepository):

    def __init__(self, uri: str, db_name: str, product_collection=None):
        self._client = MongoClient(uri)
        self._db = self._client[db_name]
        self._collection = self._db['category']
        self._product_collection = product_collection
        self._collection.create_index(
            [('title', ASCENDING)],
            unique=True,
            name='unique_title',
            collation={'locale': 'en', 'strength': 2},
        )

    # Add category to MongoDB document
    def add(self, category: dict) -> dict:
        doc = dict(category)
        try:
            self._collection.insert_one(doc)
        except DuplicateKeyError:
            raise DuplicateError('Category with this title already exists')
        return self.to_dict(doc)

    # Get category by ID
    def get_by_id(self, category_id: str):
        doc = self._collection.find_one({
            '_id': ObjectId(category_id),
            'is_deleted': {'$ne': True},
        })
        if doc is None:
            return None
        return self.to_dict(doc)

    # List categories with pagination
    def list_paginated(self, page_size: int, after=None, search: str | None = None) -> dict:
        query: dict = {'is_deleted': {'$ne': True}}
        if after is not None:
            query['_id'] = {'$lt': ObjectId(after)}
        if search:
            escaped = re.escape(search.strip().lower())
            query['title'] = {'$regex': f'^{escaped}', '$options': 'i'}
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

    # Update category in MongoDB document
    def update(self, category_id: str, changes: dict) -> dict | None:
        set_fields = {}
        unset_fields = {}
        for key, value in changes.items():
            if key in ('_id', 'id'):
                continue
            elif key == 'description' and not value:
                unset_fields[key] = ''
            else:
                set_fields[key] = value

        update_op: dict = {}
        if set_fields:
            update_op['$set'] = set_fields
        if unset_fields:
            update_op['$unset'] = unset_fields
        if not update_op:
            return self.get_by_id(category_id)

        try:
            doc = self._collection.find_one_and_update(
                {'_id': ObjectId(category_id), 'is_deleted': {'$ne': True}},
                update_op,
                return_document=ReturnDocument.AFTER,
            )
        except DuplicateKeyError:
            raise DuplicateError('Category with this name already exists')
        if doc is None:
            return None
        return self.to_dict(doc)

    # Delete category from MongoDB document
    def delete(self, category_id: str) -> None:
        self._collection.update_one(
            {'_id': ObjectId(category_id)},
            {'$set': {'is_deleted': True}},
        )

    def title_exists(self, title: str, exclude_id=None) -> bool:
        query: dict = {
            'title': title,
            'is_deleted': {'$ne': True},
        }
        if exclude_id is not None:
            query['_id'] = {'$ne': ObjectId(exclude_id)}
        return self._collection.count_documents(query, limit=1) > 0

    def count_products_per_category(self, titles: list) -> dict:
        if not titles or self._product_collection is None:
            return dict.fromkeys(titles, 0)
        pipeline = [
            {'$match': {'category': {'$in': titles}, 'is_deleted': {'$ne': True}}},
            {'$group': {'_id': '$category', 'count': {'$sum': 1}}},
        ]
        counts = {doc['_id']: doc['count'] for doc in self._product_collection.aggregate(pipeline)}
        return {title: counts.get(title, 0) for title in titles}

    @staticmethod
    def to_dict(doc: dict) -> dict:
        cleaned = dict(doc)
        if '_id' in cleaned:
            cleaned['id'] = str(cleaned.pop('_id'))
        return cleaned


def make_category_repository():
    client = MongoClient(settings.MONGO_URI)
    db = client[settings.MONGO_DB_NAME]
    return MongoCategoryRepository(
        uri=settings.MONGO_URI,
        db_name=settings.MONGO_DB_NAME,
        product_collection=db['products'],
    )

category_repository = make_category_repository()
