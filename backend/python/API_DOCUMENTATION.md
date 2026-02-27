# Inventory API Documentation

## Overview

This is a RESTful API for managing product inventory. The API provides endpoints for creating, reading, updating, deleting, and listing products.

**Base URL**: `http://localhost:8000/inventory/`

**Content Type**: `application/json`

---

## Table of Contents

1. [Authentication](#authentication)
2. [Product Model](#product-model)
3. [Request Tracing](#request-tracing)
4. [Endpoints](#endpoints)
   - [Create Product](#1-create-product)
   - [Get Product](#2-get-product)
   - [List Products](#3-list-products)
   - [Update Product](#4-update-product)
   - [Delete Product](#5-delete-product)
5. [Pagination](#pagination)
6. [Error Handling](#error-handling)
7. [Examples](#examples)

---

## Authentication

Currently, the API does not require authentication. This may change in future versions.

---

## Product Model

A product has the following attributes:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string (ObjectId) | Auto-generated | MongoDB ObjectId — unique identifier |
| `name` | string | **Yes** | Product name (max 255 characters) |
| `description` | string | No | Detailed product description |
| `barcode` | string | No | Unique barcode identifier. Enforced by a sparse unique index in MongoDB |
| `category` | string | No | Product category |
| `brand` | string | No | Product brand or manufacturer |
| `price` | decimal | **Yes** | Product price (minimum 0.01) |
| `quantity` | integer | No | Current quantity in stock (default: 0, minimum: 0) |
| `minimum_stock_level` | integer | No | Minimum stock before reorder alert (default: 0, minimum: 0) |
| `created_at` | datetime string | Auto-generated | ISO 8601 timestamp set on creation |
| `updated_at` | datetime string | Auto-updated | ISO 8601 timestamp updated on every change |

> **Note**: Product IDs are MongoDB ObjectIds represented as 24-character hex strings (e.g. `"65f1a2b3c4d5e6f7a8b9c0d1"`). Passing a non-ObjectId string as an ID returns `400 Bad Request`.

---

## Request Tracing

Every request is assigned a unique `X-Request-ID` header (UUIDv4). The middleware:
- Reads an incoming `X-Request-ID` header if provided (pass-through mode for distributed tracing).
- Generates a new UUID if none is present.
- Echoes the ID back in the response `X-Request-ID` header.
- Injects the ID into every structured log line for the duration of the request.

---

## Endpoints

### 1. Create Product

Create a new product in the inventory.

**Endpoint**: `POST /inventory/products/`

**Request Body**:
```json
{
  "name": "Product Name",
  "price": "99.99",
  "description": "Product description (optional)",
  "barcode": "123456789 (optional)",
  "category": "Electronics (optional)",
  "brand": "Brand Name (optional)",
  "quantity": 100,
  "minimum_stock_level": 10
}
```

**Success Response**:
- **Code**: `201 Created`
- **Body**:
```json
{
  "id": "65f1a2b3c4d5e6f7a8b9c0d1",
  "name": "Product Name",
  "description": "Product description",
  "barcode": "123456789",
  "category": "Electronics",
  "brand": "Brand Name",
  "price": 99.99,
  "quantity": 100,
  "minimum_stock_level": 10,
  "created_at": "2026-02-26T10:30:00.000000",
  "updated_at": "2026-02-26T10:30:00.000000"
}
```

**Error Responses**:
- **Code**: `400 Bad Request` — Missing required fields (`name`, `price`), invalid data types or values, or duplicate barcode
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
    "category": "Electronics",
    "brand": "TechBrand",
    "price": "1299.99",
    "quantity": 50,
    "minimum_stock_level": 5
  }'
```

---

### 2. Get Product

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
  "category": "Electronics",
  "brand": "Brand Name",
  "price": 99.99,
  "quantity": 100,
  "minimum_stock_level": 10,
  "created_at": "2026-02-26T10:30:00.000000",
  "updated_at": "2026-02-26T10:30:00.000000"
}
```

**Error Responses**:
- **Code**: `400 Bad Request` — Invalid ObjectId format
- **Code**: `404 Not Found` — Product does not exist (or has been soft-deleted)
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

### 3. List Products

Retrieve a paginated list of products with optional filtering and search.

**Endpoint**: `GET /inventory/products/`

**Query Parameters** (all optional):
- `category`: Filter products by an exact category string
- `search`: Case-insensitive substring search across `name`, `barcode`, and `description`
- `page_size`: Number of items per page (default: `10`, minimum: `1`, maximum: `100`)
- `after`: Cursor for the next page — use the value from the `next` URL returned in the previous response

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
      "category": "Electronics",
      "brand": "Brand A",
      "price": 99.99,
      "quantity": 100,
      "minimum_stock_level": 10,
      "created_at": "2026-02-26T10:30:00.000000",
      "updated_at": "2026-02-26T10:30:00.000000"
    }
  ]
}
```

> `next` is `null` when there are no more pages.

**Error Responses**:
- **Code**: `400 Bad Request` — Invalid `page_size` or `after` cursor
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

4. Filter by category:
```bash
curl "http://localhost:8000/inventory/products/?category=Electronics&page_size=10"
```

5. Search with pagination:
```bash
curl "http://localhost:8000/inventory/products/?search=laptop&page_size=5"
```

6. Combine all filters:
```bash
curl "http://localhost:8000/inventory/products/?category=Electronics&search=laptop&page_size=10"
```

---

### 4. Update Product

Update an existing product (partial or full update).

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
  "category": "Electronics",
  "brand": "Brand Name",
  "price": 109.99,
  "quantity": 150,
  "minimum_stock_level": 10,
  "created_at": "2026-02-26T10:30:00.000000",
  "updated_at": "2026-02-26T12:00:00.000000"
}
```

**Error Responses**:
- **Code**: `400 Bad Request` — Invalid ObjectId, invalid field values, or duplicate barcode
- **Code**: `404 Not Found` — Product does not exist
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
- **Code**: `400 Bad Request` — Invalid ObjectId format
- **Code**: `404 Not Found` — Product does not exist
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

## Pagination

The list endpoint uses **cursor-based (keyset) pagination** sorted newest → oldest using MongoDB `_id` (which embeds a creation timestamp).

**Why cursor-based?**
- Stable: inserting or deleting documents between requests does not cause items to be skipped or duplicated.
- Efficient: the query uses the default `_id` index — no extra sorting index needed.

**How to paginate**:

1. Make the first request — omit `after`:
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
| `results` | Array of product objects |

---

## Error Handling

The API uses standard HTTP status codes and returns error messages in the following format:

```json
{
  "error": "Descriptive error message"
}
```

### Common HTTP Status Codes

| Code | Description |
|------|-------------|
| `200` | OK — Request succeeded |
| `201` | Created — Resource created successfully |
| `204` | No Content — Request succeeded (delete) |
| `400` | Bad Request — Validation error, invalid ID format, or duplicate barcode |
| `404` | Not Found — Product does not exist or has been deleted |
| `500` | Internal Server Error — Unexpected server error |

### Common Error Scenarios

1. **Validation Errors**: Missing required fields (`name`, `price`), invalid data types, values out of range
2. **Invalid ID**: A product ID that is not a valid 24-character MongoDB ObjectId hex string
3. **Not Found**: Accessing a product that does not exist or has been soft-deleted
4. **Duplicate Barcode**: Creating or updating a product with a barcode that already belongs to another active product

---

## Examples

### Complete Workflow Example

#### 1. Create a new product
```bash
curl -X POST http://localhost:8000/inventory/products/ \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Wireless Mouse",
    "description": "Ergonomic wireless mouse with USB receiver",
    "barcode": "MOUSE001",
    "category": "Electronics",
    "brand": "TechCorp",
    "price": "29.99",
    "quantity": 250,
    "minimum_stock_level": 25
  }'
```

Response:
```json
{
  "id": "65f1a2b3c4d5e6f7a8b9c0d1",
  "name": "Wireless Mouse",
  "description": "Ergonomic wireless mouse with USB receiver",
  "barcode": "MOUSE001",
  "category": "Electronics",
  "brand": "TechCorp",
  "price": 29.99,
  "quantity": 250,
  "minimum_stock_level": 25,
  "created_at": "2026-02-26T14:30:00.000000",
  "updated_at": "2026-02-26T14:30:00.000000"
}
```

#### 2. Get the product
```bash
curl http://localhost:8000/inventory/products/65f1a2b3c4d5e6f7a8b9c0d1/
```

#### 3. Update the stock quantity
```bash
curl -X PATCH "http://localhost:8000/inventory/products/65f1a2b3c4d5e6f7a8b9c0d1/" \
  -H "Content-Type: application/json" \
  -d '{"quantity": 200}'
```

#### 4. List all electronics (first page)
```bash
curl "http://localhost:8000/inventory/products/?category=Electronics&page_size=10"
```

#### 5. Delete the product
```bash
curl -X DELETE "http://localhost:8000/inventory/products/65f1a2b3c4d5e6f7a8b9c0d1/"
```

---

## PowerShell Examples

For Windows PowerShell users:

### Create Product
```powershell
$body = @{
    name = "Wireless Mouse"
    description = "Ergonomic wireless mouse"
    barcode = "MOUSE001"
    category = "Electronics"
    brand = "TechCorp"
    price = "29.99"
    quantity = 250
    minimum_stock_level = 25
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://localhost:8000/inventory/products/" `
  -Method POST `
  -ContentType "application/json" `
  -Body $body
```

### Get Product
```powershell
Invoke-RestMethod -Uri "http://localhost:8000/inventory/products/65f1a2b3c4d5e6f7a8b9c0d1/" `
  -Method GET
```

### List Products
```powershell
Invoke-RestMethod -Uri "http://localhost:8000/inventory/products/?page_size=10" `
  -Method GET
```

### Update Product
```powershell
$body = @{
    quantity = 200
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://localhost:8000/inventory/products/65f1a2b3c4d5e6f7a8b9c0d1/" `
  -Method PATCH `
  -ContentType "application/json" `
  -Body $body
```

### Delete Product
```powershell
Invoke-RestMethod -Uri "http://localhost:8000/inventory/products/65f1a2b3c4d5e6f7a8b9c0d1/" `
  -Method DELETE
```

---

## Python Examples

Using the `requests` library:

```python
import requests

BASE_URL = "http://localhost:8000/inventory"

# Create a product
def create_product():
    data = {
        "name": "Wireless Mouse",
        "description": "Ergonomic wireless mouse",
        "barcode": "MOUSE001",
        "category": "Electronics",
        "brand": "TechCorp",
        "price": "29.99",
        "quantity": 250,
        "minimum_stock_level": 25,
    }
    response = requests.post(f"{BASE_URL}/products/", json=data)
    return response.json()

# Get a product
def get_product(product_id):
    response = requests.get(f"{BASE_URL}/products/{product_id}/")
    return response.json()

# List all products (first page)
def list_products(category=None, search=None, page_size=10, after=None):
    params = {"page_size": page_size}
    if category:
        params["category"] = category
    if search:
        params["search"] = search
    if after:
        params["after"] = after
    response = requests.get(f"{BASE_URL}/products/", params=params)
    return response.json()

# Iterate all pages
def list_all_products(category=None, search=None, page_size=10):
    after = None
    while True:
        page = list_products(category=category, search=search, page_size=page_size, after=after)
        yield from page["results"]
        if page["next"] is None:
            break
        # Extract the 'after' cursor from the next URL
        from urllib.parse import urlparse, parse_qs
        after = parse_qs(urlparse(page["next"]).query)["after"][0]

# Update a product
def update_product(product_id, data):
    response = requests.patch(f"{BASE_URL}/products/{product_id}/", json=data)
    return response.json()

# Delete a product
def delete_product(product_id):
    response = requests.delete(f"{BASE_URL}/products/{product_id}/")
    return response.status_code  # 204

# Example usage
if __name__ == "__main__":
    product = create_product()
    print(f"Created: {product}")

    product_id = product["id"]
    print(f"Fetched: {get_product(product_id)}")

    page = list_products()
    print(f"First page ({page['count']} items), next={page['next']}")

    print(f"Updated: {update_product(product_id, {'quantity': 200})}")

    status = delete_product(product_id)
    print(f"Deleted — HTTP {status}")
```

---

## Notes

- All timestamps are ISO 8601 strings in local server time (no timezone suffix)
- Products are ordered newest-first by default (sorted by MongoDB `_id` descending)
- The `barcode` field must be unique across all **active** (non-deleted) products
- `price` must be ≥ 0.01
- `quantity` and `minimum_stock_level` cannot be negative
- A `WARNING` log is emitted automatically when `quantity ≤ minimum_stock_level` after a create or update
- Deleted products are not physically removed from MongoDB; they are filtered out by an `is_deleted: true` flag

