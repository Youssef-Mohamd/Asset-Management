# Asset Management System

Backend API for **DarkAtlas Attack Surface Monitoring (ASM)** — the module at the heart of Buguard's platform that continuously discovers and tracks an organization's internet-facing assets.

## 📋 Overview

This is a **Backend Engineering Track** implementation providing a complete REST API for the Asset Management module. The system:

- **Models & stores** discovered assets (domains, subdomains, IP addresses, services, certificates, technologies)
- **Tracks lifecycle** — first_seen, last_seen, status transitions (active → stale → archived)
- **Manages relationships** — builds the asset graph (subdomains → domains, services → IPs, etc.)
- **Deduplicates** on import — re-importing the same asset updates metadata, not duplicates
- **Provides search & filtering** — by type, status, tag, value; with pagination and sorting
- **Protects write operations** — API key authentication on POST/PATCH/DELETE
- **Validates rigorously** — Pydantic validation on input, business logic validation in services, DB constraints

---

## 🚀 Quick Start

### Prerequisites
- Docker & Docker Compose (recommended)
- OR Python 3.11+ + PostgreSQL 14+

### Option 1: Docker (Recommended)

```bash
# Clone and enter directory
cd Asset-Management

# Start everything (API + PostgreSQL)
docker-compose up -d

# Wait for health check (~10s)
curl http://localhost:8000/health

# View API docs
open http://localhost:8000/docs
```

**Stop:**
```bash
docker-compose down
```

### Option 2: Local Development

```bash
# 1. Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Set up environment
cp .env.example .env
# Edit .env with your DATABASE_URL and API_KEY

# 4. Create database (assuming PostgreSQL is running)
# Migrations handled automatically on first run

# 5. Run the API
uvicorn app.main:app --reload
```

The API will be available at `http://localhost:8000`

---

## 🔐 Authentication

All **write operations** (POST, PATCH, DELETE) require an API key in the `X-API-Key` header.

### Generate an API Key

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

### Using the API Key

```bash
# Example: Create an asset
curl -X POST http://localhost:8000/assets \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key-here" \
  -d '{
    "type": "domain",
    "value": "example.com",
    "source": "manual",
    "tags": ["prod"]
  }'
```

### Environment Setup

Create a `.env` file (see `.env.example`):

```bash
DATABASE_URL=postgresql://user:password@localhost:5432/asset_management
API_KEY=your-secure-api-key-here
DEBUG=false
```

**Never commit the `.env` file!** It's in `.gitignore`.

---

## 📚 API Documentation

### Full Docs
- **Swagger UI**: `http://localhost:8000/docs`
- **ReDoc**: `http://localhost:8000/redoc`
- **OpenAPI JSON**: `http://localhost:8000/openapi.json`

### Core Endpoints

#### Assets

| Method | Endpoint | Description | Auth |
|--------|----------|-------------|------|
| GET | `/assets` | List all assets with filters, search, sort, pagination | ❌ |
| POST | `/assets` | Create a new asset | ✅ |
| GET | `/assets/{id}` | Get a single asset | ❌ |
| PATCH | `/assets/{id}` | Update an asset | ✅ |
| DELETE | `/assets/{id}` | Delete an asset | ✅ |

#### Bulk Operations

| Method | Endpoint | Description | Auth |
|--------|----------|-------------|------|
| POST | `/assets/bulk` | Bulk import with deduplication | ✅ |

#### Lifecycle

| Method | Endpoint | Description | Auth |
|--------|----------|-------------|------|
| POST | `/assets/{id}/activate` | Reactivate a stale asset | ✅ |
| POST | `/assets/mark-stale` | Mark inactive assets as stale | ✅ |

#### Relationships

| Method | Endpoint | Description | Auth |
|--------|----------|-------------|------|
| POST | `/relationships` | Create a relationship between assets | ✅ |
| GET | `/assets/{id}/relationships` | Get all relationships for an asset | ❌ |
| GET | `/assets/{id}/graph` | Get asset + related assets (the graph) | ❌ |

---

## 📋 Examples

### 1. Create an Asset

```bash
curl -X POST http://localhost:8000/assets \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key" \
  -d '{
    "type": "domain",
    "value": "example.com",
    "source": "scan",
    "tags": ["prod", "root"],
    "metadata": {
      "discovered_date": "2024-01-15"
    }
  }'
```

**Response:**
```json
{
  "id": "a1e3f2c1-1234-5678-9abc-def012345678",
  "type": "domain",
  "value": "example.com",
  "status": "active",
  "first_seen": "2024-01-15T10:30:00Z",
  "last_seen": "2024-01-15T10:30:00Z",
  "source": "scan",
  "tags": ["prod", "root"],
  "metadata": {"discovered_date": "2024-01-15"},
  "created_at": "2024-01-15T10:30:00Z",
  "updated_at": "2024-01-15T10:30:00Z"
}
```

### 2. List Assets with Filtering

```bash
# Get all active subdomains tagged "prod", page 1, 20 per page
curl "http://localhost:8000/assets?type=subdomain&status=active&tag=prod&page=1&limit=20"
```

### 3. Bulk Import with Deduplication

```bash
curl -X POST http://localhost:8000/assets/bulk \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key" \
  -d '{
    "assets": [
      {"type": "domain", "value": "example.com", "source": "scan"},
      {"type": "subdomain", "value": "api.example.com", "source": "scan"},
      {"type": "ip_address", "value": "203.0.113.10", "source": "scan"}
    ]
  }'
```

**Response:**
```json
{
  "created": 3,
  "updated": 0,
  "duplicates": 0,
  "total": 3
}
```

### 4. Create a Relationship

```bash
curl -X POST http://localhost:8000/relationships \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key" \
  -d '{
    "from_asset_id": "a1e3f2c1-1234-5678-9abc-def012345678",
    "to_asset_id": "b2e4f3d2-2345-6789-0def-012345678901",
    "relation_type": "parent"
  }'
```

### 5. Get Asset Graph

```bash
curl "http://localhost:8000/assets/a1e3f2c1-1234-5678-9abc-def012345678/graph"
```

**Response:**
```json
{
  "asset": { ... },
  "relationships": [
    {
      "id": "rel-id",
      "from_asset_id": "...",
      "to_asset_id": "...",
      "relation_type": "parent"
    }
  ],
  "related_assets": [ ... ],
  "relation_count": 1
}
```

---

## 🧪 Testing

Run the test suite:

```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ -v --cov=app --cov-report=html

# Run specific test class
pytest tests/test_main.py::TestAssetCRUD -v

# Run specific test
pytest tests/test_main.py::TestAssetCRUD::test_create_asset -v
```

**Test Coverage:**
- ✅ CRUD operations (create, read, update, delete)
- ✅ Deduplication logic (bulk import, upsert)
- ✅ Lifecycle management (mark stale, activate)
- ✅ Relationships (creation, retrieval, graph)
- ✅ API endpoints
- ✅ Pagination & filtering

---

## 🏗️ Architecture & Design

### Project Structure

```
Asset-Management/
├── app/
│   ├── __init__.py
│   ├── main.py           # FastAPI routes & error handling
│   ├── models.py         # SQLAlchemy ORM models
│   ├── schemas.py        # Pydantic validation schemas
│   ├── services.py       # Business logic (CRUD, dedup, etc.)
│   ├── database.py       # Database session & connection
│   ├── config.py         # Configuration from .env
│   └── auth.py           # API key authentication
├── tests/
│   └── test_main.py      # Comprehensive test suite
├── Dockerfile            # Container image
├── docker-compose.yml    # Local development setup
├── requirements.txt      # Python dependencies
├── .env.example          # Environment template
├── .gitignore            # Git ignore rules
└── README.md             # This file
```

### Data Model

**Core Assets:**
- `domain` — apex domain (example.com)
- `subdomain` — subdomain (api.example.com)
- `ip_address` — IPv4 or IPv6 (203.0.113.10)
- `service` — port + protocol + banner (443/tcp)
- `certificate` — TLS certificate (CN, issuer, expiry)
- `technology` — software/framework (nginx 1.21.0)

**Asset Attributes:**
- `id` — UUID, stable identifier
- `type` — enum (domain, subdomain, etc.)
- `value` — canonical representation
- `status` — active | stale | archived
- `first_seen` — datetime (set once)
- `last_seen` — datetime (updated on re-sighting)
- `source` — scan | import | manual
- `tags` — list of labels (prod, staging, etc.)
- `metadata` — JSON, type-specific fields
- `created_at`, `updated_at` — audit timestamps

**Relationships:**
- `id` — UUID
- `from_asset_id`, `to_asset_id` — asset IDs
- `relation_type` — string (parent, resolves_to, hosts, etc.)

---

## 🔄 Deduplication & Lifecycle

### Idempotent Imports

Importing the same dataset twice produces the same result:

```bash
# First import
POST /assets/bulk with [domain:example.com, subdomain:api.example.com]
→ created: 2, updated: 0, duplicates: 0

# Second import (identical data)
POST /assets/bulk with [domain:example.com, subdomain:api.example.com]
→ created: 0, updated: 2, duplicates: 0  ← No duplicates created
```

**How it works:**
1. **Batch dedup**: Removes duplicates within the request
2. **DB lookup**: Queries for (type, value) in existing data
3. **Upsert**: Updates last_seen, merges metadata/tags if exists; creates if new

### Asset Lifecycle

```
Created (active)
    ↓
    ├─→ [Updated] → last_seen advances
    ├─→ [Not seen for 30 days] → mark-stale endpoint → stale
    └─→ stale
        └─→ [Seen again or activate endpoint] → active
```

---

## ✅ Validation & Error Handling

### Input Validation (Pydantic)
- Asset value: non-empty, max 500 chars
- Source: one of [scan, import, manual]
- Status: one of [active, stale, archived]
- Tags: list of non-empty strings
- Relationships: different from/to assets

### Business Logic Validation (Services)
- Asset exists check before creating relationships
- Prevent self-relationships
- Prevent duplicate relationships
- Merge metadata intelligently on upsert

### Error Responses

```json
{
  "detail": "Request validation failed",
  "error_code": "VALIDATION_ERROR",
  "errors": [...],
  "timestamp": "2024-01-15T10:30:00Z"
}
```

**HTTP Status Codes:**
- `200` OK
- `201` Created
- `204` No Content (deleted)
- `400` Bad Request (validation, business logic)
- `401` Unauthorized (missing/invalid API key)
- `404` Not Found
- `409` Conflict (duplicate asset)
- `500` Internal Server Error

---

## 📦 Deployment

### Docker Compose

```bash
docker-compose up -d
```

Sets up:
- **PostgreSQL 15** on `5432` (internal: postgres:5432)
- **FastAPI** on `8000` (maps to localhost)
- Automatic health checks


---

## 🎯 Design Decisions & Assumptions

### Deduplication Strategy
Assets are identified by **(type, value)** pair. This means:
- `domain:example.com` and `subdomain:example.com` are different assets
- Re-importing the same asset updates `last_seen` and merges metadata
- Metadata merge is shallow (`dict.update()`); tags are replaced (not merged)

### Status Enum
Three states: `active`, `stale`, `archived`
- **active**: Currently seen or recently discovered
- **stale**: Not seen for N days (marked by `/mark-stale` endpoint)
- **archived**: Explicitly archived or deleted by user

### Relationships
- Directional: `from_asset_id` → `to_asset_id`
- Not restricted by asset type (API enforces no self-relationships)
- Duplicates not allowed (enforced in services)

### Pagination Defaults
- **Limit**: 20 (max: 100)
- **Page**: 1 (1-indexed)
- Prevents accidental full-table retrieval

### Authentication
- **API key only** (no JWT, no user management)
- Suitable for backend-to-backend or service-to-service auth

---


### Running Locally

```bash
# Install editable mode for development
pip install -e .

# Run with auto-reload
uvicorn app.main:app --reload --port 8000

# Watch logs
tail -f debug.log
```

---

## 

- **API Docs**: http://localhost:8000/docs
- **Issues**: File issues with error messages and steps to reproduce
- **Tests**: Run `pytest tests/ -v` to ensure everything works



---


