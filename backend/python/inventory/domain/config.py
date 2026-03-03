# Product field defaults
DEFAULT_MINIMUM_STOCK_LEVEL = 0
DEFAULT_DESCRIPTION = ''
DEFAULT_BARCODE = ''
DEFAULT_CATEGORY = ''
DEFAULT_BRAND = ''

# Required/allowed fields
REQUIRED_CREATE_FIELDS = ['name', 'price', 'quantity', 'brand']
ALLOWED_UPDATE_FIELDS = [
    'name', 'description', 'barcode', 'category', 'brand',
    'price', 'quantity', 'minimum_stock_level',
]

# Category field defaults
DEFAULT_CATEGORY_DESCRIPTION = ''
CATEGORY_REQUIRED_CREATE_FIELDS = ['title']
CATEGORY_ALLOWED_UPDATE_FIELDS = ['title', 'description']

# Not-found messages
PRODUCT_NOT_FOUND_MESSAGE = 'Product not found'
CATEGORY_NOT_FOUND_MESSAGE = 'Category not found'

# Pagination defaults
DEFAULT_PAGE = 1
DEFAULT_PAGE_SIZE = 10
MIN_PAGE_SIZE = 1
MAX_PAGE_SIZE = 100

# Bulk CSV defaults
CSV_REQUIRED_COLUMNS = ['name', 'price', 'quantity', 'brand']
CSV_ALLOWED_COLUMNS = [
    'name', 'price', 'quantity', 'brand',
    'description', 'barcode', 'category', 'minimum_stock_level',
]
CSV_UPDATE_REQUIRED_COLUMNS = ['id']
CSV_UPDATE_ALLOWED_COLUMNS = ['id'] + ALLOWED_UPDATE_FIELDS
CSV_DELETE_REQUIRED_COLUMNS = ['id']
CSV_DELETE_ALLOWED_COLUMNS = ['id']
CSV_MAX_ROWS = 1000
CSV_EMPTY_FILE_MESSAGE = 'CSV file is empty or contains only a header row'
CSV_MISSING_COLUMNS_MESSAGE = 'CSV is missing required columns'
CSV_TOO_MANY_ROWS_MESSAGE = f'CSV must not exceed {CSV_MAX_ROWS} rows'
CSV_ROW_LIMIT_EXCEEDED_LOG = 'CSV row limit exceeded'
CSV_NO_FILE_MESSAGE = 'No CSV file provided'
CSV_INVALID_FORMAT_MESSAGE = 'Uploaded file is not a valid CSV'
