from decimal import Decimal, InvalidOperation
from .exceptions import ValidationError

def validate_required_fields(data, required_fields):
    for field in required_fields:
        if field not in data:
            raise ValidationError(f'Missing required field: {field}')


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
        return int(raw_id)
    except (ValueError, TypeError):
        raise ValidationError('Invalid product ID')


def validate_pagination(raw_page, raw_page_size):
    try:
        page = int(raw_page) if raw_page is not None else 1
        page_size = int(raw_page_size) if raw_page_size is not None else 10
    except (ValueError, TypeError):
        raise ValidationError('Invalid page or page_size parameter')
    if page < 1:
        raise ValidationError('Page number must be greater than 0')
    if page_size < 1 or page_size > 100:
        raise ValidationError('Page size must be between 1 and 100')

    return page, page_size
