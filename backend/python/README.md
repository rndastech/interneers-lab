# Inventory Management API — Interneers Lab 2026

A **Product Inventory Management REST API** built with **Django** and **Django REST Framework**, following **Hexagonal Architecture** (Ports & Adapters) principles. This project is part of the Rippling Interneers Lab 2026 backend module.

---

## Table of Contents

1. [Overview](#overview)
2. [Hexagonal Architecture](#hexagonal-architecture)
   - [Why Hexagonal Architecture?](#why-hexagonal-architecture)
   - [How It's Applied in This Project](#how-its-applied-in-this-project)
   - [Project Structure Breakdown](#project-structure-breakdown)
   - [Data Flow](#data-flow)
3. [Features](#features)
4. [Tech Stack](#tech-stack)
5. [API Endpoints](#api-endpoints)
6. [Getting Started](#getting-started)
   - [Prerequisites](#prerequisites)
   - [Installation](#installation)
   - [Running the Server](#running-the-server)
   - [Running with Docker (Full Stack)](#running-with-docker-full-stack)
7. [Observability: ELK Stack Logging](#observability-elk-stack-logging)
   - [Architecture](#logging-architecture)
   - [Log Format](#log-format)
   - [Viewing Logs in Kibana](#viewing-logs-in-kibana)
8. [Developer Guide](#developer-guide)
   - [Adding a New Field to Product](#adding-a-new-field-to-product)
   - [Swapping the Storage Backend](#swapping-the-storage-backend)
   - [Adding a New Endpoint](#adding-a-new-endpoint)
9. [Testing](#testing)
10. [Further Reading](#further-reading)

---

## Overview

This API allows you to manage a product inventory with full CRUD (Create, Read, Update, Delete) operations. Products have attributes such as name, price, quantity, barcode, category, brand, and minimum stock level. The API also supports **search**, **category filtering**, and **cursor-based pagination** out of the box.

The application uses **MongoDB** as its persistent data store, accessed through a clean adapter that implements the `ProductRepository` port. The architecture is designed so that swapping to a different database (PostgreSQL, etc.) requires changes **only** in the adapter layer, without touching any business logic.

All API activity is logged in **structured JSON** to a rotating log file, which is shipped to **Elasticsearch** by **Filebeat** and visualised in **Kibana** — a full ELK stack observability pipeline running via Docker Compose.

---

## Hexagonal Architecture

### Why Hexagonal Architecture?

Traditional Django projects tend to couple business logic tightly with Django models, views, and ORM queries. This makes the code hard to test in isolation, hard to migrate to a different database, and hard to reason about as complexity grows.

**Hexagonal Architecture** (also known as **Ports & Adapters**) solves these problems by enforcing a clear separation of concerns:

- **The core domain** (business rules, validation, data structures) has **zero dependencies** on Django, databases, or HTTP frameworks.
- **Ports** define abstract interfaces that the domain expects from the outside world (e.g., "I need a way to store and retrieve products").
- **Adapters** provide concrete implementations of those ports (e.g., "Here's how to store products in memory" or "Here's how to store products in MongoDB").

This means:
- ✅ Business logic can be **unit-tested** without a database or HTTP server
- ✅ You can **swap storage backends** by writing a new adapter — no changes to domain or service code
- ✅ The codebase stays **modular and maintainable** as it scales
- ✅ Django-specific code (views, serializers) stays thin and only handles HTTP translation

### How It's Applied in This Project

```
┌─────────────────────────────────────────────────────────────────┐
│                        HTTP Layer (Django)                       │
│   views.py — translates HTTP requests/responses                 │
│   urls.py  — maps URLs to view functions                        │
└─────────────────────┬───────────────────────────────────────────┘
                      │  calls
                      ▼
┌─────────────────────────────────────────────────────────────────┐
│                     Service Layer                                │
│   services/product_service.py                                   │
│   — orchestrates business logic                                 │
│   — calls validators and repository (via port interface)        │
└─────────────────────┬───────────────────────────────────────────┘
                      │  depends on (abstraction)
                      ▼
┌─────────────────────────────────────────────────────────────────┐
│                     Domain Layer (Pure Python)                   │
│   domain/product.py     — Product dataclass                     │
│   domain/validators.py  — validation functions                  │
│   domain/exceptions.py  — custom exception classes              │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                     Port (Abstract Interface)                    │
│   ports/repository.py                                           │
│   — defines ProductRepository ABC                               │
│   — declares: add, get_by_id, update, delete, etc.   │
└─────────────────────┬───────────────────────────────────────────┘
                      │  implemented by
                      ▼
┌─────────────────────────────────────────────────────────────────┐
│                     Adapters (Concrete Implementations)          │
│   adapters/mongo_repository.py                                  │
│   — stores products in MongoDB (soft-delete, cursor pagination) │
│   — implements the ProductRepository interface                  │
│                                                                 │
│   adapters/python_logger.py                                     │
│   — implements ProductLogger port via Python's logging module   │
│   — JSONFormatter emits ECS-compatible JSON for Filebeat        │
└─────────────────────────────────────────────────────────────────┘
```

### Project Structure Breakdown

```
inventory/
├── domain/                  # 🧠 Core Domain — NO external dependencies
│   ├── product.py           #    Product dataclass with to_dict/from_dict
│   ├── validators.py        #    Pure validation functions (price, quantity, cursor pagination, etc.)
│   ├── exceptions.py        #    Custom exceptions: ValidationError, NotFoundError, DuplicateError
│   ├── config.py            #    Constants: required fields, allowed update fields, defaults
│   └── request_context.py   #    Thread-local request ID storage
│
├── ports/                   # 🔌 Ports — Abstract interfaces
│   ├── repository.py        #    ProductRepository ABC (add, get, list_paginated, update, delete, barcode_exists)
│   └── logger.py            #    ProductLogger ABC (debug, info, warning, error, critical)
│
├── adapters/                # 🔧 Adapters — Concrete implementations
│   ├── mongo_repository.py  #    MongoProductRepository (MongoDB, soft-delete, cursor pagination)
│   └── python_logger.py     #    PythonProductLogger + JSONFormatter (ECS-compatible structured logging)
│
├── services/                # ⚙️ Application Services — Orchestration layer
│   └── product_service.py   #    ProductService (create, get, list, update, delete, low_stock_check)
│
├── middleware/              # 🔗 Django Middleware
│   └── request_id.py        #    RequestIDMiddleware — injects/propagates X-Request-ID header
│
├── views.py                 # 🌐 Django Views — HTTP request/response translation
└── urls.py                  # 🗺️ URL routing
```

### Data Flow

Here's what happens when a user creates a product:

1. **`POST /inventory/products/`** hits the `products_list_create` view
2. `RequestIDMiddleware` assigns a unique `X-Request-ID` to the request (propagated to all log entries)
3. The view delegates to `ProductService.create_product(data)`
4. The service calls **validators** (from `domain/validators.py`) to check required fields, price, quantity, etc.
5. The service checks **barcode uniqueness** via the repository port
6. The service constructs a `Product` dataclass (from `domain/product.py`)
7. The service calls `repository.add(product.to_dict())` — through the **port interface**
8. The **adapter** (`MongoProductRepository`) persists the document in MongoDB
9. The dict representation flows back up through the service → view → HTTP response
10. Every step is logged in structured JSON; Filebeat tails the log file and ships entries to Elasticsearch

At no point does the domain or service layer know it's using MongoDB. It only knows it's calling methods on a `ProductRepository`.

---

## Features

- **Full CRUD** — Create, Read, Update, Delete products
- **Search** — Full-text search across product name, barcode, and description (MongoDB regex, case-insensitive)
- **Category filtering** — Filter product listings by category
- **Cursor-based pagination** — Stable keyset pagination using MongoDB `_id` (newest-first); `?page_size=` (1–100, default 10) and `?after=<cursor>` query params; response includes a `next` URL ready to follow
- **Barcode uniqueness** — Enforced at the MongoDB index level (sparse unique index) and validated in the service layer
- **Soft delete** — Deleted products are flagged with `is_deleted: true` in MongoDB and hidden from all queries
- **Low-stock warnings** — Automatic `WARNING` log emitted whenever a product's quantity is at or below its `minimum_stock_level`
- **Input validation** — Price, quantity, minimum stock level, MongoDB ObjectId, and pagination parameters
- **Custom error handling** — Structured JSON error responses with appropriate HTTP status codes
- **Request ID tracing** — `RequestIDMiddleware` injects a UUID `X-Request-ID` header into every request and response; the ID propagates through all structured log entries
- **Structured JSON logging** — All log lines are ECS-compatible JSON (Elastic Common Schema), written to a rotating `inventory.log` file
- **ELK stack observability** — Filebeat ships logs to Elasticsearch; Kibana provides dashboards and search (all via Docker Compose)
- **MongoDB persistence** — Data stored in MongoDB 8.0 via `MongoProductRepository`; swapping to another database only requires a new adapter
- **Hexagonal architecture** — Clean separation of concerns for testability and maintainability

---

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Language | Python 3.12+ |
| Web Framework | Django 6.0.2 |
| API Framework | Django REST Framework |
| Data Storage | MongoDB 8.0 (`MongoProductRepository`) |
| Logging | Python `logging` + custom `JSONFormatter` (ECS-compatible) |
| Log Shipping | Filebeat 8.13.4 |
| Log Indexing | Elasticsearch 8.13.4 |
| Log Visualisation | Kibana 8.13.4 |
| Containerisation | Docker & Docker Compose |

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/inventory/products/` | Create a new product |
| `GET` | `/inventory/products/` | List products (supports `?category=`, `?search=`, `?page_size=`, `?after=`) |
| `GET` | `/inventory/products/<id>/` | Get a product by MongoDB ObjectId |
| `PUT/PATCH` | `/inventory/products/<id>/` | Update a product (full or partial) |
| `DELETE` | `/inventory/products/<id>/` | Delete a product (soft delete) |

> For full request/response examples, see [API_DOCUMENTATION.md](./API_DOCUMENTATION.md).

---

## Getting Started

### Prerequisites

- **Python 3.12+**
- **pip** (Python package manager)
- **Docker & Docker Compose** (required for MongoDB + ELK stack)

### Installation

1. **Clone the repository** and navigate to the backend folder:
   ```bash
   cd backend/python
   ```

2. **Create and activate a virtual environment**:
   ```bash
   # macOS / Linux
   python3 -m venv venv
   source venv/bin/activate

   # Windows
   python -m venv venv
   .\venv\Scripts\activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Run migrations** (for Django's internal tables):
   ```bash
   python manage.py migrate
   ```

### Running the Server

Start the full infrastructure stack first (MongoDB + ELK):
```bash
docker-compose up -d
```

Then start the Django development server:
```bash
python manage.py runserver
```

The API will be available at **http://localhost:8000/inventory/**.

### Running with Docker (Full Stack)

`docker-compose up -d` starts the following services:

| Service | Description | Port |
|---------|-------------|------|
| `mongodb` | MongoDB 8.0 — primary data store | `27019` (host) → `27017` (container) |
| `elasticsearch` | Elasticsearch 8.13.4 — log index | `9200` |
| `kibana` | Kibana 8.13.4 — log visualisation UI | `5601` |
| `filebeat-setup` | One-shot container: sets up Filebeat index templates | — |
| `filebeat` | Filebeat 8.13.4 — tails `inventory.log` and ships to Elasticsearch | — |

**MongoDB connection** (default, overridable via environment variables):
- URI: `mongodb://root:example@localhost:27019/`
- Database: `inventory_db`

Override via environment variables before starting the server:
```bash
export MONGO_URI="mongodb://root:example@localhost:27019/"
export MONGO_DB_NAME="inventory_db"
```

---

## Observability: ELK Stack Logging

### Logging Architecture

```
Django App
    │
    │  Python logging (JSONFormatter → ECS-compatible JSON)
    ▼
inventory.log  (rotating file, up to 5 MB × 3 backups)
    │
    │  Filebeat tails the file
    ▼
Elasticsearch 8.13.4
    │
    │  Kibana queries
    ▼
Kibana 8.13.4  →  http://localhost:5601
```

### Log Format

Every log line is a single JSON object. Example:

```json
{
  "@timestamp": "2026-02-26T10:15:30.123Z",
  "log": { "level": "INFO", "logger": "inventory.views" },
  "level": "INFO",
  "logger": "inventory.views",
  "request_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "message": "HTTP 201 - product created",
  "service": { "name": "inventory-api" },
  "labels": {
    "product_id": "65f1a2b3c4d5e6f7a8b9c0d1"
  }
}
```

Key fields:
| Field | Description |
|-------|-------------|
| `@timestamp` | ISO 8601 UTC timestamp (millisecond precision) |
| `request_id` | UUID injected by `RequestIDMiddleware`; echoed in `X-Request-ID` response header |
| `level` | Log level: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` |
| `logger` | Python logger name (e.g. `inventory.views`, `inventory.services.product_service`) |
| `message` | Human-readable event description |
| `labels` | Arbitrary structured context (product ID, barcode, error message, etc.) |
| `exception` | Formatted traceback (only present on `ERROR`/`CRITICAL` with `exc_info=True`) |

### Viewing Logs in Kibana

1. Ensure the full stack is running: `docker-compose up -d`
2. Open **http://localhost:5601** in your browser
3. Navigate to **Discover** — logs are indexed under `filebeat-*`
4. Filter by `request_id` to trace a single HTTP request end-to-end
5. Filter by `level: WARNING` to see all low-stock alerts

---

