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
   - [Running with Docker](#running-with-docker)
7. [Developer Guide](#developer-guide)
   - [Adding a New Field to Product](#adding-a-new-field-to-product)
   - [Swapping the Storage Backend](#swapping-the-storage-backend)
   - [Adding a New Endpoint](#adding-a-new-endpoint)
8. [Testing](#testing)
9. [Further Reading](#further-reading)

---

## Overview

This API allows you to manage a product inventory with full CRUD (Create, Read, Update, Delete) operations. Products have attributes such as name, price, quantity, barcode, category, brand, and minimum stock level. The API also supports **search**, **category filtering**, and **pagination** out of the box.

Currently, the application uses an **in-memory data store** — meaning all data lives in Python dictionaries at runtime and resets when the server restarts. This is intentional: the architecture is designed so that swapping to a persistent database (MongoDB, PostgreSQL, etc.) requires changes **only** in the adapter layer, without touching any business logic.

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
│   — declares: add, get_by_id, list_all, update, delete, etc.   │
└─────────────────────┬───────────────────────────────────────────┘
                      │  implemented by
                      ▼
┌─────────────────────────────────────────────────────────────────┐
│                     Adapter (Concrete Implementation)            │
│   adapters/in_memory_repository.py                              │
│   — stores products in a Python dictionary                      │
│   — implements the ProductRepository interface                  │
└─────────────────────────────────────────────────────────────────┘
```

### Project Structure Breakdown

```
inventory/
├── domain/                  # 🧠 Core Domain — NO external dependencies
│   ├── product.py           #    Product dataclass with to_dict/from_dict
│   ├── validators.py        #    Pure validation functions (price, quantity, pagination, etc.)
│   └── exceptions.py        #    Custom exceptions: ValidationError, NotFoundError, DuplicateError
│
├── ports/                   # 🔌 Ports — Abstract interfaces
│   └── repository.py        #    ProductRepository ABC (add, get, list, update, delete, barcode_exists)
│
├── adapters/                # 🔧 Adapters — Concrete implementations
│   └── in_memory_repository.py  #  InMemoryProductRepository (dict-based storage)
│
├── services/                # ⚙️ Application Services — Orchestration layer
│   └── product_service.py   #    ProductService (create, get, list, update, delete)
│
├── views.py                 # 🌐 Django Views — HTTP request/response translation
├── urls.py                  # 🗺️ URL routing
├── models.py                # (empty — not using Django ORM for now)
├── serializers.py           # (empty — serialization handled by domain dataclass)
└── tests.py                 # Test suite
```

### Data Flow

Here's what happens when a user creates a product:

1. **`POST /inventory/products/create/`** hits `views.py::create_product()`
2. The view delegates to `ProductService.create_product(data)`
3. The service calls **validators** (from `domain/validators.py`) to check required fields, price, quantity, etc.
4. The service checks **barcode uniqueness** via the repository port
5. The service constructs a `Product` dataclass (from `domain/product.py`)
6. The service calls `repository.add(product.to_dict())` — through the **port interface**
7. The **adapter** (`InMemoryProductRepository`) stores it in a Python dict
8. The dict representation flows back up through the service → view → HTTP response

At no point does the domain or service layer know it's using an in-memory dict. It only knows it's calling methods on a `ProductRepository`.

---

## Features

- **Full CRUD** — Create, Read, Update, Delete products
- **Search** — Full-text search across product name, barcode, and description
- **Category filtering** — Filter product listings by category
- **Pagination** — Configurable page size (1–100), default 10 per page
- **Barcode uniqueness** — Enforced unique barcodes across all products
- **Input validation** — Price, quantity, minimum stock level, product ID, and pagination parameters
- **Custom error handling** — Structured JSON error responses with appropriate HTTP status codes
- **Hexagonal architecture** — Clean separation of concerns for testability and maintainability

---

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Language | Python 3.12+ |
| Web Framework | Django 6.0.2 |
| API Framework | Django REST Framework |
| Data Storage | In-memory (Python dict) — swappable to MongoDB/PostgreSQL |
| Database (planned) | MongoDB 8.0 (via Docker Compose) |
| Containerization | Docker & Docker Compose |

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/inventory/products/create/` | Create a new product |
| `GET` | `/inventory/products/detail/?id=<id>` | Get a product by ID |
| `GET` | `/inventory/products/` | List products (supports `?category=`, `?search=`, `?page=`, `?page_size=`) |
| `PUT/PATCH` | `/inventory/products/update/?id=<id>` | Update a product |
| `DELETE` | `/inventory/products/delete/?id=<id>` | Delete a product |

> For full request/response examples, see [API_DOCUMENTATION.md](./API_DOCUMENTATION.md).

---

## Getting Started

### Prerequisites

- **Python 3.12+** (3.14 recommended)
- **pip** (Python package manager)
- **Docker & Docker Compose** (optional, for MongoDB)

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

```bash
python manage.py runserver
```

The API will be available at **http://localhost:8000/inventory/**.

### Running with Docker

Start MongoDB (for future use when a MongoDB adapter is added):
```bash
docker-compose up -d
```

This starts a MongoDB 8.0 instance on port **27019** with credentials `root` / `example`.

---

