from decimal import Decimal, InvalidOperation
from bson import ObjectId
from bson.errors import InvalidId
from .exceptions import ValidationError
from inventory.domain.config import (
    DEFAULT_PAGE,
    DEFAULT_PAGE_SIZE,
    MIN_PAGE_SIZE,
    MAX_PAGE_SIZE,
    CSV_REQUIRED_COLUMNS,
    CSV_UPDATE_REQUIRED_COLUMNS,
    CSV_DELETE_REQUIRED_COLUMNS,
    CSV_EMPTY_FILE_MESSAGE,
    CSV_MISSING_COLUMNS_MESSAGE,
    CSV_TOO_MANY_ROWS_MESSAGE,
    CSV_MAX_ROWS,
)


def validate_required_fields(data, required_fields):
    missing_fields = [
        field for field in required_fields
        if field not in data or str(data[field]).strip() == ''
    ]
    if missing_fields:
        raise ValidationError(f'Missing required fields: {", ".join(missing_fields)}')


def validate_price(raw_price):
    try:
        price = Decimal(str(raw_price))
        if price <= 0:
            raise ValidationError('Price must be greater than 0')
        return price
    except (ValueError, TypeError, InvalidOperation):
        raise ValidationError('Invalid price format')


def validate_quantity(raw_quantity):
    try:
        quantity = int(raw_quantity)
        if quantity < 0:
            raise ValidationError('Quantity cannot be negative')
        return quantity
    except (ValueError, TypeError):
        raise ValidationError('Invalid quantity format')


def validate_minimum_stock_level(raw_minimum_stock_level):
    try:
        minimum_stock_level = int(raw_minimum_stock_level)
        if minimum_stock_level < 0:
            raise ValidationError('Minimum stock level cannot be negative')
        return minimum_stock_level
    except (ValueError, TypeError):
        raise ValidationError('Invalid minimum stock level format')


def validate_product_id(raw_id):
    if raw_id is None:
        raise ValidationError('Product ID is required')
    try:
        ObjectId(str(raw_id))
        return str(raw_id)
    except (InvalidId, TypeError):
        raise ValidationError('Invalid product ID')


def validate_cursor_pagination(raw_page_size, raw_after):
    try:
        page_size = int(raw_page_size) if raw_page_size is not None else DEFAULT_PAGE_SIZE
    except (ValueError, TypeError):
        raise ValidationError('Invalid page_size parameter')
    if page_size < MIN_PAGE_SIZE or page_size > MAX_PAGE_SIZE:
        raise ValidationError(f'Page size must be between {MIN_PAGE_SIZE} and {MAX_PAGE_SIZE}')

    after = None
    if raw_after is not None:
        try:
            ObjectId(str(raw_after))
            after = str(raw_after)
        except Exception:
            raise ValidationError('Invalid cursor value for "after" parameter')

    return page_size, after


def validate_category_id(raw_id):
    if raw_id is None:
        raise ValidationError('Category ID is required')
    try:
        ObjectId(str(raw_id))
        return str(raw_id)
    except (InvalidId, TypeError):
        raise ValidationError('Invalid category ID')


def check_csv_rows(rows, required_columns):
    if not rows:
        raise ValidationError(CSV_EMPTY_FILE_MESSAGE)
    if len(rows) > CSV_MAX_ROWS:
        raise ValidationError(CSV_TOO_MANY_ROWS_MESSAGE)
    headers = rows[0].keys()
    missing = [col for col in required_columns if col not in headers]
    if missing:
        raise ValidationError(f"{CSV_MISSING_COLUMNS_MESSAGE}: {', '.join(missing)}")


def validate_csv_create(rows: list) -> None:
    check_csv_rows(rows, CSV_REQUIRED_COLUMNS)


def validate_csv_update(rows: list) -> None:
    check_csv_rows(rows, CSV_UPDATE_REQUIRED_COLUMNS)


def validate_csv_delete(rows: list) -> None:
    check_csv_rows(rows, CSV_DELETE_REQUIRED_COLUMNS)
