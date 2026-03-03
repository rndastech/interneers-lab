from datetime import datetime
from inventory.domain.category import Category
from inventory.domain.validators import (
    validate_category_id,
    validate_required_fields,
    validate_cursor_pagination,
)
from inventory.domain.exceptions import NotFoundError, DuplicateError, ValidationError
from inventory.ports.category_repository import CategoryRepository
from inventory.ports.logger import ProductLogger
from inventory.domain.config import (
    CATEGORY_REQUIRED_CREATE_FIELDS,
    CATEGORY_ALLOWED_UPDATE_FIELDS,
    DEFAULT_CATEGORY_DESCRIPTION,
    CATEGORY_NOT_FOUND_MESSAGE,
)


class CategoryService:

    def __init__(self, repository: CategoryRepository, logger: ProductLogger):
        self._repo = repository
        self._logger = logger

    def validate_title_uniqueness(self, title: str, exclude_id=None):
        if title and self._repo.title_exists(title, exclude_id=exclude_id):
            self._logger.error(
                'Duplicate title rejected',
                title=title,
                exclude_id=exclude_id,
            )
            raise DuplicateError('Category with this title already exists')

    def create_category(self, data: dict) -> dict:
        self._logger.debug('create_category called', incoming_fields=list(data.keys()))

        validate_required_fields(data, CATEGORY_REQUIRED_CREATE_FIELDS)
        title = data['title'].strip().lower()
        self.validate_title_uniqueness(title)

        now = datetime.now().isoformat()
        category = Category(
            title=title,
            description=data.get('description', DEFAULT_CATEGORY_DESCRIPTION),
            created_at=now,
            updated_at=now,
        )
        saved = self._repo.add(category.to_dict())

        self._logger.info('Category created successfully', category_id=saved['id'])
        return saved

    def get_category(self, raw_id) -> dict:
        self._logger.debug('get_category called', raw_id=raw_id)

        category_id = validate_category_id(raw_id)
        category = self._repo.get_by_id(category_id)
        if category is None:
            self._logger.error('Category not found', category_id=category_id)
            raise NotFoundError(CATEGORY_NOT_FOUND_MESSAGE)

        self._logger.info('Category retrieved', category_id=category_id)
        return category

    def list_categories(self, raw_page_size=None, raw_after=None, search=None) -> dict:
        self._logger.debug(
            'list_categories called',
            raw_page_size=raw_page_size,
            raw_after=raw_after,
            search=search,
        )

        page_size, after = validate_cursor_pagination(raw_page_size, raw_after)
        result = self._repo.list_paginated(page_size=page_size, after=after, search=search)
        titles = [cat['title'] for cat in result['results']]
        counts = self._repo.count_products_per_category(titles)
        for cat in result['results']:
            cat['product_count'] = counts.get(cat['title'], 0)

        self._logger.info(
            'Category list returned',
            page_size=page_size,
            after=after,
            search=search,
            returned_count=len(result['results']),
            has_next=result['next_cursor'] is not None,
        )
        return result

    def update_category(self, raw_id, data: dict) -> dict:
        self._logger.debug(
            'update_category called',
            raw_id=raw_id,
            fields_to_update=list(data.keys()),
        )

        category_id = validate_category_id(raw_id)
        category = self._repo.get_by_id(category_id)
        if category is None:
            self._logger.error('Category not found for update', category_id=category_id)
            raise NotFoundError(CATEGORY_NOT_FOUND_MESSAGE)

        if 'title' in data and data['title'] != category.get('title'):
            data['title'] = data['title'].strip().lower()
            self.validate_title_uniqueness(data['title'], exclude_id=category_id)

        updated_fields = [field for field in CATEGORY_ALLOWED_UPDATE_FIELDS if field in data]
        changes = {field: data[field] for field in CATEGORY_ALLOWED_UPDATE_FIELDS if field in data}
        changes['updated_at'] = datetime.now().isoformat()

        saved = self._repo.update(category_id, changes)
        if saved is None:
            self._logger.error('Concurrent delete during update', category_id=category_id)
            raise NotFoundError(CATEGORY_NOT_FOUND_MESSAGE)

        self._logger.info(
            'Category updated successfully',
            category_id=category_id,
            updated_fields=updated_fields,
        )
        return saved

    def delete_category(self, raw_id) -> None:
        self._logger.debug('delete_category called', raw_id=raw_id)

        category_id = validate_category_id(raw_id)
        category = self._repo.get_by_id(category_id)
        if category is None:
            self._logger.error('Category not found for deletion', category_id=category_id)
            raise NotFoundError(CATEGORY_NOT_FOUND_MESSAGE)

        self._repo.delete(category_id)
        self._logger.info('Category deleted', category_id=category_id)
