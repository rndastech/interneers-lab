# Product field defaults
DEFAULT_MINIMUM_STOCK_LEVEL = 0
DEFAULT_DESCRIPTION = ''
DEFAULT_BARCODE = ''
DEFAULT_CATEGORY = ''
DEFAULT_BRAND = ''

# Required/allowed fields
REQUIRED_CREATE_FIELDS = ['name', 'price', 'quantity']
ALLOWED_UPDATE_FIELDS = [
    'name', 'description', 'barcode', 'category', 'brand',
    'price', 'quantity', 'minimum_stock_level',
]

# Pagination defaults
DEFAULT_PAGE = 1
DEFAULT_PAGE_SIZE = 10
MIN_PAGE_SIZE = 1
MAX_PAGE_SIZE = 100
