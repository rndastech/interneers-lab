# Inventory API Documentation

## Overview

This is a RESTful API for managing product inventory and categories. The API provides endpoints for creating, reading, updating, deleting, and listing products and categories, as well as bulk CSV operations on products.

**Base URL**: `http://localhost:8000/inventory/`

**Content Type**: `application/json`

---

## Table of Contents

1. [Authentication](#authentication)
2. [Data Models](#data-models)
   - [Product Model](#product-model)
   - [Category Model](#category-model)
3. [Request Tracing](#request-tracing)
4. [Endpoints](#endpoints)
   - [Products](#products)
     - [Create Product](#1-create-product)
     - [List Products](#2-list-products)
     - [Get Product](#3-get-product)
     - [Update Product](#4-update-product)
     - [Delete Product](#5-delete-product)
     - [Bulk Create from CSV](#6-bulk-create-products-from-csv)
     - [Bulk Update from CSV](#7-bulk-update-products-from-csv)
     - [Bulk Delete from CSV](#8-bulk-delete-products-from-csv)
   - [Categories](#categories)
     - [Create Category](#9-create-category)
     - [List Categories](#10-list-categories)
     - [Get Category](#11-get-category)
     - [Update Category](#12-update-category)
     - [Delete Category](#13-delete-category)
5. [Endpoint Summary](#endpoint-summary)
6. [Pagination](#pagination)
7. [Error Handling](#error-handling)
8. [Examples](#examples)

---

## Authentication

Currently, the API does not require authentication. This may change in future versions.

---

## Data Models

### Product Model

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string (ObjectId) | Auto-generated | MongoDB ObjectId ΓÇö unique identifier |
| `name` | string | **Yes** | Product name (max 255 characters) |
| `description` | string | No | Detailed product description (default: `""`) |
| `barcode` | string | No | Unique barcode identifier. Enforced by a sparse unique index (default: `""`) |
| `category` | string | No | Category title (must match an existing category, stored lowercase). Default: `""` |
| `brand` | string | No | Product brand or manufacturer (default: `""`) |
| `price` | decimal | **Yes** | Product price (minimum 0.01) |
| `quantity` | integer | **Yes** | Current quantity in stock (minimum: 0) |
| `minimum_stock_level` | integer | No | Minimum stock before reorder alert (default: 0, minimum: 0) |
| `created_at` | datetime string | Auto-generated | ISO 8601 timestamp set on creation |
| `updated_at` | datetime string | Auto-updated | ISO 8601 timestamp updated on every change |

> **Note**: Product IDs are MongoDB ObjectIds represented as 24-character hex strings (e.g. `"65f1a2b3c4d5e6f7a8b9c0d1"`). Passing a non-ObjectId string as an ID returns `400 Bad Request`.

> **Note**: The `category` field stores the lowercased title of an existing category. If the provided category title does not match any active category, the request returns `404 Not Found`.

### Category Model

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string (ObjectId) | Auto-generated | MongoDB ObjectId ΓÇö unique identifier |
| `title` | string | **Yes** | Category title ΓÇö must be unique (stored lowercase) |
| `description` | string | **Yes** | Category description |
| `created_at` | datetime string | Auto-generated | ISO 8601 timestamp set on creation |
| `updated_at` | datetime string | Auto-updated | ISO 8601 timestamp updated on every change |

> **Note**: Category titles are normalised to lowercase and must be unique across all active categories.

---

## Request Tracing

Every request is assigned a unique `X-Request-ID` header (UUIDv4). The middleware:
- Reads an incoming `X-Request-ID` header if provided (pass-through mode for distributed tracing).
- Generates a new UUID if none is present.
- Echoes the ID back in the response `X-Request-ID` header.
- Injects the ID into every structured log line for the duration of the request.

---

## Endpoints

### Products

---

### 1. Create Product

Create a new product in the inventory.

**Endpoint**: `POST /inventory/products/`

**Request Body**:
```json
{
  "name": "Product Name",
  "price": "99.99",
  "quantity": 100,
  "description": "Product description (optional)",
  "barcode": "123456789 (optional)",
  "category": "electronics (optional ΓÇö must match an existing category title)",
  "brand": "Brand Name (optional)",
  "minimum_stock_level": 10
}
```

**Required fields**: `name`, `price`, `quantity`

**Success Response**:
- **Code**: `201 Created`
- **Body**:
```json
{
  "id": "65f1a2b3c4d5e6f7a8b9c0d1",
  "name": "Product Name",
  "description": "Product description",
  "barcode": "123456789",
  "category": "electronics",
  "brand": "Brand Name",
  "price": 99.99,
  "quantity": 100,
  "minimum_stock_level": 10,
  "created_at": "2026-03-03T10:30:00.000000",
  "updated_at": "2026-03-03T10:30:00.000000"
}
```

**Error Responses**:
- **Code**: `400 Bad Request` ΓÇö Missing required fields (`name`, `price`, `quantity`), invalid data types/values, or duplicate barcode
- **Code**: `404 Not Found` ΓÇö The specified `category` title does not match any existing category
- **Body**:
```json
{
  "error": "Error message describing the issue"
}
```

**Example**:
```bash
curl -X POST http://localhost:8000/inventory/products/ \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Laptop",
    "description": "High-performance laptop",
    "barcode": "LAP001",
    "category": "electronics",
    "brand": "TechBrand",
    "price": "1299.99",
    "quantity": 50,
    "minimum_stock_level": 5
  }'
```

---

### 2. List Products

Retrieve a paginated list of products with optional filtering and search.

**Endpoint**: `GET /inventory/products/`

**Query Parameters** (all optional):

| Parameter | Type | Description |
|-----------|------|-------------|
| `category` | string (repeatable) | Filter by category title. Can be specified multiple times to filter by multiple categories (OR logic) |
| `search` | string | Case-insensitive substring search across `name`, `barcode`, and `description` |
| `page_size` | integer | Number of items per page (default: `10`, min: `1`, max: `100`) |
| `after` | string | Cursor for the next page ΓÇö use the value from the `next` URL in the previous response |

> See [Pagination](#pagination) for a detailed explanation of the cursor-based scheme.

**Success Response**:
- **Code**: `200 OK`
- **Body**:
```json
{
  "count": 10,
  "page_size": 10,
  "next": "http://localhost:8000/inventory/products/?page_size=10&after=65f1a2b3c4d5e6f7a8b9c0d1",
  "results": [
    {
      "id": "65f1a2b3c4d5e6f7a8b9c0d1",
      "name": "Product 1",
      "description": "Description 1",
      "barcode": "123456789",
      "category": "electronics",
      "brand": "Brand A",
      "price": 99.99,
      "quantity": 100,
      "minimum_stock_level": 10,
      "created_at": "2026-03-03T10:30:00.000000",
      "updated_at": "2026-03-03T10:30:00.000000"
    }
  ]
}
```

> `next` is `null` when there are no more pages.

**Error Responses**:
- **Code**: `400 Bad Request` ΓÇö Invalid `page_size` or `after` cursor
- **Body**:
```json
{
  "error": "Error message describing the issue"
}
```

**Examples**:

1. First page (default 10 items, newest first):
```bash
curl http://localhost:8000/inventory/products/
```

2. Custom page size:
```bash
curl "http://localhost:8000/inventory/products/?page_size=20"
```

3. Next page using cursor:
```bash
curl "http://localhost:8000/inventory/products/?page_size=10&after=65f1a2b3c4d5e6f7a8b9c0d1"
```

4. Filter by a single category:
```bash
curl "http://localhost:8000/inventory/products/?category=electronics"
```

5. Filter by multiple categories:
```bash
curl "http://localhost:8000/inventory/products/?category=electronics&category=furniture"
```

6. Search with pagination:
```bash
curl "http://localhost:8000/inventory/products/?search=laptop&page_size=5"
```

7. Combine all filters:
```bash
curl "http://localhost:8000/inventory/products/?category=electronics&search=laptop&page_size=10"
```

---

### 3. Get Product

Retrieve a single product by its MongoDB ObjectId.

**Endpoint**: `GET /inventory/products/<product_id>/`

**Path Parameters**:
- `product_id` (required): The product's MongoDB ObjectId (24-character hex string)

**Success Response**:
- **Code**: `200 OK`
- **Body**:
```json
{
  "id": "65f1a2b3c4d5e6f7a8b9c0d1",
  "name": "Product Name",
  "description": "Product description",
  "barcode": "123456789",
  "category": "electronics",
  "brand": "Brand Name",
  "price": 99.99,
  "quantity": 100,
  "minimum_stock_level": 10,
  "created_at": "2026-03-03T10:30:00.000000",
  "updated_at": "2026-03-03T10:30:00.000000"
}
```

**Error Responses**:
- **Code**: `400 Bad Request` ΓÇö Invalid ObjectId format
- **Code**: `404 Not Found` ΓÇö Product does not exist or has been soft-deleted
- **Body**:
```json
{
  "error": "Error message describing the issue"
}
```

**Example**:
```bash
curl http://localhost:8000/inventory/products/65f1a2b3c4d5e6f7a8b9c0d1/
```

---

### 4. Update Product

Update an existing product. Both `PUT` (full intent) and `PATCH` (partial update) are accepted ΓÇö only the fields present in the request body are updated.

**Endpoint**: `PUT /inventory/products/<product_id>/` or `PATCH /inventory/products/<product_id>/`

**Path Parameters**:
- `product_id` (required): The product's MongoDB ObjectId

**Request Body** (include only the fields you want to update):
```json
{
  "name": "Updated Product Name",
  "description": "Updated description",
  "price": "109.99",
  "quantity": 150
}
```

**Updatable fields**: `name`, `description`, `barcode`, `category`, `brand`, `price`, `quantity`, `minimum_stock_level`

**Success Response**:
- **Code**: `200 OK`
- **Body**: The full updated product object
```json
{
  "id": "65f1a2b3c4d5e6f7a8b9c0d1",
  "name": "Updated Product Name",
  "description": "Updated description",
  "barcode": "123456789",
  "category": "electronics",
  "brand": "Brand Name",
  "price": 109.99,
  "quantity": 150,
  "minimum_stock_level": 10,
  "created_at": "2026-03-03T10:30:00.000000",
  "updated_at": "2026-03-03T12:00:00.000000"
}
```

**Error Responses**:
- **Code**: `400 Bad Request` ΓÇö Invalid ObjectId, invalid field values, or duplicate barcode
- **Code**: `404 Not Found` ΓÇö Product does not exist, or the specified `category` does not exist
- **Body**:
```json
{
  "error": "Error message describing the issue"
}
```

**Example**:
```bash
curl -X PATCH "http://localhost:8000/inventory/products/65f1a2b3c4d5e6f7a8b9c0d1/" \
  -H "Content-Type: application/json" \
  -d '{
    "price": "1399.99",
    "quantity": 45
  }'
```

---

### 5. Delete Product

Soft-delete a product from the inventory. The document is flagged `is_deleted: true` in MongoDB and hidden from all subsequent reads and listings.

**Endpoint**: `DELETE /inventory/products/<product_id>/`

**Path Parameters**:
- `product_id` (required): The product's MongoDB ObjectId

**Success Response**:
- **Code**: `204 No Content`
- **Body**:
```json
{
  "message": "Product deleted successfully"
}
```

**Error Responses**:
- **Code**: `400 Bad Request` ΓÇö Invalid ObjectId format
- **Code**: `404 Not Found` ΓÇö Product does not exist or has already been deleted
- **Body**:
```json
{
  "error": "Error message describing the issue"
}
```

**Example**:
```bash
curl -X DELETE "http://localhost:8000/inventory/products/65f1a2b3c4d5e6f7a8b9c0d1/"
```

---

### 6. Bulk Create Products from CSV

Create multiple products in one request by uploading a CSV file.

**Endpoint**: `POST /inventory/products/csv/`

**Content-Type**: `multipart/form-data`

**Form Fields**:
- `file` (required): A CSV file where each row represents a product to create.

**CSV Columns**: `name`, `price`, `quantity`, `description`, `barcode`, `category`, `brand`, `minimum_stock_level`

**Success Response** (all rows valid):
- **Code**: `201 Created`
- **Body**:
```json
{
  "created_count": 3,
  "error_count": 0,
  "created": [
    { "id": "65f1a2b3c4d5e6f7a8b9c0d1", "name": "Product A", "...": "..." }
  ],
  "errors": []
}
```

**Partial Success Response** (some rows have errors):
- **Code**: `207 Multi-Status`
- **Body**:
```json
{
  "created_count": 2,
  "error_count": 1,
  "created": [
    { "id": "65f1a2b3c4d5e6f7a8b9c0d1", "name": "Product A", "...": "..." }
  ],
  "errors": [
    { "row": 3, "error": "Missing required field: price" }
  ]
}
```

**Error Responses**:
- **Code**: `400 Bad Request` ΓÇö No file provided or file is not a valid CSV
- **Body**:
```json
{
  "error": "Error message describing the issue"
}
```

**Example**:
```bash
curl -X POST http://localhost:8000/inventory/products/csv/ \
  -F "file=@products.csv"
```

---

### 7. Bulk Update Products from CSV

Update multiple products in one request by uploading a CSV file. Both `PUT` and `PATCH` are accepted.

**Endpoint**: `PUT /inventory/products/csv/` or `PATCH /inventory/products/csv/`

**Content-Type**: `multipart/form-data`

**Form Fields**:
- `file` (required): A CSV file where each row represents a product to update.

**CSV Columns**: `id` (required), plus any updatable fields: `name`, `price`, `quantity`, `description`, `barcode`, `category`, `brand`, `minimum_stock_level`

**Success Response** (all rows valid):
- **Code**: `200 OK`
- **Body**:
```json
{
  "updated_count": 2,
  "error_count": 0,
  "updated": [
    { "id": "65f1a2b3c4d5e6f7a8b9c0d1", "name": "Updated A", "...": "..." }
  ],
  "errors": []
}
```

**Partial Success Response** (some rows have errors):
- **Code**: `207 Multi-Status`
- **Body**:
```json
{
  "updated_count": 1,
  "error_count": 1,
  "updated": [
    { "id": "65f1a2b3c4d5e6f7a8b9c0d1", "name": "Updated A", "...": "..." }
  ],
  "errors": [
    { "row": 2, "error": "Product not found" }
  ]
}
```

**Error Responses**:
- **Code**: `400 Bad Request` ΓÇö No file provided or file is not a valid CSV
- **Body**:
```json
{
  "error": "Error message describing the issue"
}
```

**Example**:
```bash
curl -X PATCH http://localhost:8000/inventory/products/csv/ \
  -F "file=@updates.csv"
```

---

### 8. Bulk Delete Products from CSV

Delete multiple products in one request by uploading a CSV file.

**Endpoint**: `DELETE /inventory/products/csv/`

**Content-Type**: `multipart/form-data`

**Form Fields**:
- `file` (required): A CSV file where each row contains a product `id` to delete.

**CSV Columns**: `id` (required)

**Success Response** (all rows valid):
- **Code**: `200 OK`
- **Body**:
```json
{
  "deleted_count": 3,
  "error_count": 0,
  "deleted": ["65f1a2b3c4d5e6f7a8b9c0d1", "65f1a2b3c4d5e6f7a8b9c0d2"],
  "errors": []
}
```

**Partial Success Response** (some rows have errors):
- **Code**: `207 Multi-Status`
- **Body**:
```json
{
  "deleted_count": 2,
  "error_count": 1,
  "deleted": ["65f1a2b3c4d5e6f7a8b9c0d1"],
  "errors": [
    { "row": 3, "error": "Product not found" }
  ]
}
```

**Error Responses**:
- **Code**: `400 Bad Request` ΓÇö No file provided or file is not a valid CSV
- **Body**:
```json
{
  "error": "Error message describing the issue"
}
```

**Example**:
```bash
curl -X DELETE http://localhost:8000/inventory/products/csv/ \
  -F "file=@deletes.csv"
```

---

### Categories

---

### 9. Create Category

Create a new category.

**Endpoint**: `POST /inventory/categories/`

**Request Body**:
```json
{
  "title": "Electronics",
  "description": "Electronic devices and accessories"
}
```

**Required fields**: `title`, `description`

> **Note**: `title` is normalised to lowercase before storage. Duplicate titles (case-insensitive) are rejected.

**Success Response**:
- **Code**: `201 Created`
- **Body**:
```json
{
  "id": "65f1a2b3c4d5e6f7a8b9c0e1",
  "title": "electronics",
  "description": "Electronic devices and accessories",
  "created_at": "2026-03-03T10:30:00.000000",
  "updated_at": "2026-03-03T10:30:00.000000"
}
```

**Error Responses**:
- **Code**: `400 Bad Request` ΓÇö Missing required fields (`title`, `description`) or duplicate title
- **Body**:
```json
{
  "error": "Error message describing the issue"
}
```

**Example**:
```bash
curl -X POST http://localhost:8000/inventory/categories/ \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Electronics",
    "description": "Electronic devices and accessories"
  }'
```

---

### 10. List Categories

Retrieve a paginated list of categories with optional search.

**Endpoint**: `GET /inventory/categories/`

**Query Parameters** (all optional):

| Parameter | Type | Description |
|-----------|------|-------------|
| `search` | string | Case-insensitive substring search across `title` |
| `page_size` | integer | Number of items per page (default: `10`, min: `1`, max: `100`) |
| `after` | string | Cursor for the next page ΓÇö use the value from the `next` URL in the previous response |

**Success Response**:
- **Code**: `200 OK`
- **Body**:
```json
{
  "count": 5,
  "page_size": 10,
  "next": null,
  "results": [
    {
      "id": "65f1a2b3c4d5e6f7a8b9c0e1",
      "title": "electronics",
      "description": "Electronic devices and accessories",
      "created_at": "2026-03-03T10:30:00.000000",
      "updated_at": "2026-03-03T10:30:00.000000"
    }
  ]
}
```

**Error Responses**:
- **Code**: `400 Bad Request` ΓÇö Invalid `page_size` or `after` cursor
- **Body**:
```json
{
  "error": "Error message describing the issue"
}
```

**Examples**:

1. List all categories:
```bash
curl http://localhost:8000/inventory/categories/
```

2. Search categories:
```bash
curl "http://localhost:8000/inventory/categories/?search=elec"
```

3. Custom page size:
```bash
curl "http://localhost:8000/inventory/categories/?page_size=20"
```

---

### 11. Get Category

Retrieve a single category by its MongoDB ObjectId.

**Endpoint**: `GET /inventory/categories/<category_id>/`

**Path Parameters**:
- `category_id` (required): The category's MongoDB ObjectId (24-character hex string)

**Success Response**:
- **Code**: `200 OK`
- **Body**:
```json
{
  "id": "65f1a2b3c4d5e6f7a8b9c0e1",
  "title": "electronics",
  "description": "Electronic devices and accessories",
  "created_at": "2026-03-03T10:30:00.000000",
  "updated_at": "2026-03-03T10:30:00.000000"
}
```

**Error Responses**:
- **Code**: `400 Bad Request` ΓÇö Invalid ObjectId format
- **Code**: `404 Not Found` ΓÇö Category does not exist or has been soft-deleted
- **Body**:
```json
{
  "error": "Error message describing the issue"
}
```

**Example**:
```bash
curl http://localhost:8000/inventory/categories/65f1a2b3c4d5e6f7a8b9c0e1/
```

---

### 12. Update Category

Update an existing category. Both `PUT` and `PATCH` are accepted ΓÇö only the fields present in the request body are updated.

**Endpoint**: `PUT /inventory/categories/<category_id>/` or `PATCH /inventory/categories/<category_id>/`

**Path Parameters**:
- `category_id` (required): The category's MongoDB ObjectId

**Request Body** (include only the fields you want to update):
```json
{
  "title": "Consumer Electronics",
  "description": "Updated description"
}
```

**Updatable fields**: `title`, `description`

**Success Response**:
- **Code**: `200 OK`
- **Body**: The full updated category object
```json
{
  "id": "65f1a2b3c4d5e6f7a8b9c0e1",
  "title": "consumer electronics",
  "description": "Updated description",
  "created_at": "2026-03-03T10:30:00.000000",
  "updated_at": "2026-03-03T12:00:00.000000"
}
```

**Error Responses**:
- **Code**: `400 Bad Request` ΓÇö Invalid ObjectId, invalid field values, or duplicate title
- **Code**: `404 Not Found` ΓÇö Category does not exist
- **Body**:
```json
{
  "error": "Error message describing the issue"
}
```

**Example**:
```bash
curl -X PATCH "http://localhost:8000/inventory/categories/65f1a2b3c4d5e6f7a8b9c0e1/" \
  -H "Content-Type: application/json" \
  -d '{
    "description": "Updated description"
  }'
```

---

### 13. Delete Category

Soft-delete a category. The document is flagged `is_deleted: true` in MongoDB and hidden from all subsequent reads and listings.

**Endpoint**: `DELETE /inventory/categories/<category_id>/`

**Path Parameters**:
- `category_id` (required): The category's MongoDB ObjectId

**Success Response**:
- **Code**: `204 No Content`
- **Body**:
```json
{
  "message": "Category deleted successfully"
}
```

**Error Responses**:
- **Code**: `400 Bad Request` ΓÇö Invalid ObjectId format
- **Code**: `404 Not Found` ΓÇö Category does not exist or has already been deleted
- **Body**:
```json
{
  "error": "Error message describing the issue"
}
```

**Example**:
```bash
curl -X DELETE "http://localhost:8000/inventory/categories/65f1a2b3c4d5e6f7a8b9c0e1/"
```

---

## Endpoint Summary

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/inventory/products/` | Create a product |
| `GET` | `/inventory/products/` | List products (paginated, filterable) |
| `GET` | `/inventory/products/<product_id>/` | Get a product by ID |
| `PUT` / `PATCH` | `/inventory/products/<product_id>/` | Update a product |
| `DELETE` | `/inventory/products/<product_id>/` | Soft-delete a product |
| `POST` | `/inventory/products/csv/` | Bulk create products from CSV |
| `PUT` / `PATCH` | `/inventory/products/csv/` | Bulk update products from CSV |
| `DELETE` | `/inventory/products/csv/` | Bulk delete products from CSV |
| `POST` | `/inventory/categories/` | Create a category |
| `GET` | `/inventory/categories/` | List categories (paginated, searchable) |
| `GET` | `/inventory/categories/<category_id>/` | Get a category by ID |
| `PUT` / `PATCH` | `/inventory/categories/<category_id>/` | Update a category |
| `DELETE` | `/inventory/categories/<category_id>/` | Soft-delete a category |

---

## Pagination

Both list endpoints use **cursor-based (keyset) pagination** sorted newest ΓåÆ oldest using MongoDB `_id` (which embeds a creation timestamp).

**Why cursor-based?**
- Stable: inserting or deleting documents between requests does not cause items to be skipped or duplicated.
- Efficient: the query uses the default `_id` index ΓÇö no extra sorting index needed.

**How to paginate**:

1. Make the first request ΓÇö omit `after`:
   ```
   GET /inventory/products/?page_size=10
   ```
2. If the response contains a non-null `next` URL, follow it directly for the next page:
   ```
   GET /inventory/products/?page_size=10&after=65f1a2b3c4d5e6f7a8b9c0d1
   ```
3. Repeat until `next` is `null`.

**Response fields**:

| Field | Description |
|-------|-------------|
| `count` | Number of items returned in this page |
| `page_size` | Requested page size |
| `next` | Absolute URL for the next page, or `null` if this is the last page |
| `results` | Array of product or category objects |

---

## Error Handling

The API uses standard HTTP status codes and returns error messages in the following format:

```json
{
  "error": "Descriptive error message"
}
```

### HTTP Status Codes

| Code | Description |
|------|-------------|
| `200` | OK ΓÇö Request succeeded |
| `201` | Created ΓÇö Resource created successfully |
| `204` | No Content ΓÇö Resource deleted successfully |
| `207` | Multi-Status ΓÇö Bulk operation completed with partial errors |
| `400` | Bad Request ΓÇö Validation error, invalid ID format, or duplicate value |
| `404` | Not Found ΓÇö Resource does not exist, has been deleted, or a referenced resource (e.g. category) was not found |
| `500` | Internal Server Error ΓÇö Unexpected server error |

### Common Error Scenarios

1. **Validation Errors**: Missing required fields, invalid data types, values out of range
2. **Invalid ID**: An ID that is not a valid 24-character MongoDB ObjectId hex string
3. **Not Found**: Accessing a resource that does not exist or has been soft-deleted
4. **Duplicate Value**: Creating or updating with a `barcode` (products) or `title` (categories) that already belongs to another active record
5. **Referenced Resource Not Found**: Specifying a `category` on a product that does not match any existing active category
