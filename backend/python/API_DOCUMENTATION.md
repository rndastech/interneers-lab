# Inventory API Documentation

## Overview

This is a RESTful API for managing product inventory. The API provides endpoints for creating, reading, updating, deleting, and listing products.

**Base URL**: `http://localhost:8000/inventory/`

**Content Type**: `application/json`

---

## Table of Contents

1. [Authentication](#authentication)
2. [Product Model](#product-model)
3. [Endpoints](#endpoints)
   - [Create Product](#1-create-product)
   - [Get Product](#2-get-product)
   - [List Products](#3-list-products)
   - [Update Product](#4-update-product)
   - [Delete Product](#5-delete-product)
4. [Error Handling](#error-handling)
5. [Examples](#examples)

---

## Authentication

Currently, the API does not require authentication. This may change in future versions.

---

## Product Model

A product has the following attributes:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | integer | Auto-generated | Unique identifier for the product |
| `name` | string | **Yes** | Product name (max 255 characters) |
| `description` | string | No | Detailed product description |
| `barcode` | string | No | Unique barcode identifier (max 100 characters) |
| `category` | string | No | Product category (max 255 characters) |
| `brand` | string | No | Product brand or manufacturer (max 100 characters) |
| `price` | decimal | **Yes** | Product price (minimum 0.01, max 10 digits with 2 decimal places) |
| `quantity` | integer | No | Current quantity in warehouse (default: 0, minimum: 0) |
| `minimum_stock_level` | integer | No | Minimum stock level before reorder (default: 0, minimum: 0) |
| `created_at` | datetime | Auto-generated | Timestamp when product was created |
| `updated_at` | datetime | Auto-updated | Timestamp when product was last updated |

---

## Endpoints

### 1. Create Product

Create a new product in the inventory.

**Endpoint**: `POST /inventory/products/create/`

**Request Body**:
```json
{
  "name": "Product Name",
  "description": "Product description (optional)",
  "barcode": "123456789 (optional)",
  "category": "Electronics (optional)",
  "brand": "Brand Name (optional)",
  "price": "99.99",
  "quantity": 100,
  "minimum_stock_level": 10
}
```

**Success Response**:
- **Code**: `201 Created`
- **Body**:
```json
{
  "id": 1,
  "name": "Product Name",
  "description": "Product description",
  "barcode": "123456789",
  "category": "Electronics",
  "brand": "Brand Name",
  "price": "99.99",
  "quantity": 100,
  "minimum_stock_level": 10,
  "created_at": "2026-02-17T10:30:00Z",
  "updated_at": "2026-02-17T10:30:00Z"
}
```

**Error Responses**:
- **Code**: `400 Bad Request`
  - Missing required fields (name, price)
  - Invalid data types or values
  - Duplicate barcode
- **Body**:
```json
{
  "error": "Error message describing the issue"
}
```

**Example**:
```bash
curl -X POST http://localhost:8000/inventory/products/create/ \
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

Retrieve a single product by its ID.

**Endpoint**: `GET /inventory/products/detail/?id=<product_id>`

**Query Parameters**:
- `id` (required): The product ID

**Success Response**:
- **Code**: `200 OK`
- **Body**:
```json
{
  "id": 1,
  "name": "Product Name",
  "description": "Product description",
  "barcode": "123456789",
  "category": "Electronics",
  "brand": "Brand Name",
  "price": "99.99",
  "quantity": 100,
  "minimum_stock_level": 10,
  "created_at": "2026-02-17T10:30:00Z",
  "updated_at": "2026-02-17T10:30:00Z"
}
```

**Error Responses**:
- **Code**: `400 Bad Request` - Invalid or missing ID
- **Code**: `404 Not Found` - Product not found
- **Body**:
```json
{
  "error": "Error message describing the issue"
}
```

**Example**:
```bash
curl http://localhost:8000/inventory/products/detail/?id=1
```

---

### 3. List Products

Retrieve a list of all products with optional filtering and pagination.

**Endpoint**: `GET /inventory/products/`

**Query Parameters** (all optional):
- `category`: Filter products by category
- `search`: Search in product name, barcode, and description
- `page`: Page number (default: 1, minimum: 1)
- `page_size`: Number of items per page (default: 10, minimum: 1, maximum: 100)

**Success Response**:
- **Code**: `200 OK`
- **Body**:
```json
{
  "count": 25,
  "page": 1,
  "page_size": 10,
  "total_pages": 3,
  "results": [
    {
      "id": 1,
      "name": "Product 1",
      "description": "Description 1",
      "barcode": "123456789",
      "category": "Electronics",
      "brand": "Brand A",
      "price": "99.99",
      "quantity": 100,
      "minimum_stock_level": 10,
      "created_at": "2026-02-17T10:30:00Z",
      "updated_at": "2026-02-17T10:30:00Z"
    },
    {
      "id": 2,
      "name": "Product 2",
      "description": "Description 2",
      "barcode": "987654321",
      "category": "Clothing",
      "brand": "Brand B",
      "price": "49.99",
      "quantity": 200,
      "minimum_stock_level": 20,
      "created_at": "2026-02-17T11:00:00Z",
      "updated_at": "2026-02-17T11:00:00Z"
    }
  ]
}
```

**Error Responses**:
- **Code**: `400 Bad Request` - Invalid page or page_size parameter
- **Body**:
```json
{
  "error": "Error message describing the issue"
}
```

**Examples**:

1. Get all products (first page, default 10 items):
```bash
curl http://localhost:8000/inventory/products/
```

2. Get specific page:
```bash
curl http://localhost:8000/inventory/products/?page=2
```

3. Get products with custom page size:
```bash
curl http://localhost:8000/inventory/products/?page=1&page_size=20
```

4. Filter by category with pagination:
```bash
curl http://localhost:8000/inventory/products/?category=Electronics&page=1&page_size=10
```

5. Search products with pagination:
```bash
curl http://localhost:8000/inventory/products/?search=laptop&page=1&page_size=5
```

6. Combine all filters:
```bash
curl http://localhost:8000/inventory/products/?category=Electronics&search=laptop&page=1&page_size=10
```

---

### 4. Update Product

Update an existing product (partial or full update).

**Endpoint**: `PUT /inventory/products/update/?id=<product_id>` or `PATCH /inventory/products/update/?id=<product_id>`

**Query Parameters**:
- `id` (required): The product ID

**Request Body** (all fields optional, include only fields you want to update):
```json
{
  "name": "Updated Product Name",
  "description": "Updated description",
  "price": "109.99",
  "quantity": 150
}
```

**Success Response**:
- **Code**: `200 OK`
- **Body**: Updated product object
```json
{
  "id": 1,
  "name": "Updated Product Name",
  "description": "Updated description",
  "barcode": "123456789",
  "category": "Electronics",
  "brand": "Brand Name",
  "price": "109.99",
  "quantity": 150,
  "minimum_stock_level": 10,
  "created_at": "2026-02-17T10:30:00Z",
  "updated_at": "2026-02-17T12:00:00Z"
}
```

**Error Responses**:
- **Code**: `400 Bad Request` - Invalid data or duplicate barcode
- **Code**: `404 Not Found` - Product not found
- **Body**:
```json
{
  "error": "Error message describing the issue"
}
```

**Example**:
```bash
curl -X PATCH http://localhost:8000/inventory/products/update/?id=1 \
  -H "Content-Type: application/json" \
  -d '{
    "price": "1399.99",
    "quantity": 45
  }'
```

---

### 5. Delete Product

Delete a product from the inventory.

**Endpoint**: `DELETE /inventory/products/delete/?id=<product_id>`

**Query Parameters**:
- `id` (required): The product ID

**Success Response**:
- **Code**: `204 No Content`
- **Body**:
```json
{
  "message": "Product deleted successfully"
}
```

**Error Responses**:
- **Code**: `400 Bad Request` - Invalid or missing ID
- **Code**: `404 Not Found` - Product not found
- **Body**:
```json
{
  "error": "Error message describing the issue"
}
```

**Example**:
```bash
curl -X DELETE http://localhost:8000/inventory/products/delete/?id=1
```

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
| `200` | OK - Request succeeded |
| `201` | Created - Resource created successfully |
| `204` | No Content - Request succeeded with no response body |
| `400` | Bad Request - Invalid request data or validation error |
| `404` | Not Found - Resource not found |
| `500` | Internal Server Error - Server error |

### Common Error Scenarios

1. **Validation Errors**: Missing required fields, invalid data types, values out of range
2. **Not Found**: Attempting to access a product that doesn't exist
3. **Duplicate Error**: Attempting to create a product with a barcode that already exists

---

## Examples

### Complete Workflow Example

#### 1. Create a new product
```bash
curl -X POST http://localhost:8000/inventory/products/create/ \
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
  "id": 5,
  "name": "Wireless Mouse",
  "description": "Ergonomic wireless mouse with USB receiver",
  "barcode": "MOUSE001",
  "category": "Electronics",
  "brand": "TechCorp",
  "price": "29.99",
  "quantity": 250,
  "minimum_stock_level": 25,
  "created_at": "2026-02-17T14:30:00Z",
  "updated_at": "2026-02-17T14:30:00Z"
}
```

#### 2. Get the product details
```bash
curl http://localhost:8000/inventory/products/detail/?id=5
```

#### 3. Update the stock quantity
```bash
curl -X PATCH http://localhost:8000/inventory/products/update/?id=5 \
  -H "Content-Type: application/json" \
  -d '{"quantity": 200}'
```

#### 4. List all electronics
```bash
curl http://localhost:8000/inventory/products/?category=Electronics
```

#### 5. Delete the product
```bash
curl -X DELETE http://localhost:8000/inventory/products/delete/?id=5
```

---

## PowerShell Examples

For Windows PowerShell users, use `Invoke-RestMethod` or `Invoke-WebRequest`:

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

Invoke-RestMethod -Uri "http://localhost:8000/inventory/products/create/" `
  -Method POST `
  -ContentType "application/json" `
  -Body $body
```

### Get Product
```powershell
Invoke-RestMethod -Uri "http://localhost:8000/inventory/products/detail/?id=1" `
  -Method GET
```

### List Products
```powershell
Invoke-RestMethod -Uri "http://localhost:8000/inventory/products/" `
  -Method GET
```

### Update Product
```powershell
$body = @{
    quantity = 200
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://localhost:8000/inventory/products/update/?id=1" `
  -Method PATCH `
  -ContentType "application/json" `
  -Body $body
```

### Delete Product
```powershell
Invoke-RestMethod -Uri "http://localhost:8000/inventory/products/delete/?id=1" `
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
        "minimum_stock_level": 25
    }
    response = requests.post(f"{BASE_URL}/products/create/", json=data)
    return response.json()

# Get a product
def get_product(product_id):
    response = requests.get(f"{BASE_URL}/products/detail/?id={product_id}")
    return response.json()

# List all products
def list_products(category=None, search=None):
    params = {}
    if category:
        params['category'] = category
    if search:
        params['search'] = search
    response = requests.get(f"{BASE_URL}/products/", params=params)
    return response.json()

# Update a product
def update_product(product_id, data):
    response = requests.patch(
        f"{BASE_URL}/products/update/?id={product_id}",
        json=data
    )
    return response.json()

# Delete a product
def delete_product(product_id):
    response = requests.delete(f"{BASE_URL}/products/delete/?id={product_id}")
    return response.json()

# Example usage
if __name__ == "__main__":
    # Create
    product = create_product()
    print(f"Created product: {product}")
    
    # Get
    product_id = product['id']
    product_details = get_product(product_id)
    print(f"Product details: {product_details}")
    
    # List
    all_products = list_products()
    print(f"All products: {all_products}")
    
    # Update
    updated = update_product(product_id, {"quantity": 200})
    print(f"Updated product: {updated}")
    
    # Delete
    delete_product(product_id)
    print(f"Product {product_id} deleted")
```

---

## Notes

- All timestamps are in ISO 8601 format (UTC)
- Products are ordered by creation date (newest first) by default
- The `barcode` field must be unique across all products
- Price must be greater than or equal to 0.01
- Quantity and minimum_stock_level cannot be negative
- The API uses Django REST Framework for serialization and validation


