# EVE Healthcare - Diagnostic Booking & Payments Backend API

Production-ready modular Django monolith providing diagnostic test bookings, authoritative pricing snapshots, simulated payments with client idempotency, and cryptographically verified webhook reconciliation.

---

## 1. Executive Summary & What the Service Does

The **EVE Healthcare Diagnostic Booking & Payments API** is designed for a diagnostics marketplace where patients discover healthcare scan centers, schedule diagnostic tests (such as MRIs, Blood Counts, and Lipid Profiles), and pay through simulated transactions.

Unlike trivial CRUD systems, this service is engineered around **financial and transactional correctness**:
- **Authoritative Pricing**: The client *never* dictates price. The backend resolves the current price from trusted catalogue data and creates an immutable snapshot at booking time.
- **Client Idempotency**: Network retries on payment initiation replay the original result without generating duplicate bank charges.
- **Provider Webhook Deduplication**: Repeated or reordered webhook deliveries from payment gateways are processed safely via a database-enforced event ledger (`UNIQUE(event_id)`).
- **HMAC Authenticity & Freshness**: Incoming webhooks are cryptographically authenticated via HMAC-SHA256 signatures over raw request bytes and checked against a strict timestamp freshness window before payload parsing.
- **PostgreSQL Row Serialization**: Concurrency races (such as a patient cancelling an appointment at the exact millisecond a payment confirmation webhook arrives) are serialized using PostgreSQL row-level locks in a strict canonical order (`Booking -> Payment`), preventing deadlocks and state corruption.

---

## 2. Core Features

- **Identity & Authentication**: Custom UUID-based User model with normalized email identity, Argon2/PBKDF2 password hashing, anti-enumeration security, and SimpleJWT token pairs.
- **Diagnostic Catalog**: Reusable medical tests mapped to physical scan centers with center-specific pricing (`CentreTest`), location filtering, and soft deactivation.
- **Booking Engine**: Timezone-aware future scheduling, authoritative price snapshotting, ownership isolation, and a deterministic finite state machine (`PENDING`, `CONFIRMED`, `FAILED`, `CANCELLED`).
- **Simulated Payment Gateway**: Clean provider abstraction with deterministic `FakePaymentProvider`, attempt counter (`attempt_number`), and retry support for failed charges.
- **Security-First Webhook Pipeline**: Raw-body HMAC verification, replay defense, savepoint-isolated database deduplication, and non-resurrection policy for cancelled appointments.
- **Production Observability**: Request/correlation ID injection (`X-Request-ID`), privacy-first structured JSON logging (no PII or credentials logged), split liveness (`/health/live/`) and readiness (`/health/ready/`) probes.
- **API Documentation**: Automated OpenAPI 3.0 specification with interactive Swagger UI and ReDoc interfaces generated via `drf-spectacular`.

---

## 3. Technology Stack & Architectural Decisions

| Layer / Concern | Chosen Technology | Justification |
|---|---|---|
| **Language & Runtime** | Python 3.12+ | Clean, readable syntax, standard type hints, and robust async/synchronous ecosystem. |
| **Framework** | Django 5.x + DRF | Aligns directly with EVE Healthcare's public technology stack. Provides battle-tested serializers, security middleware, and ORM abstractions. |
| **Primary Database** | PostgreSQL 16 | ACID transactions, exact NUMERIC currency storage, unique indexes for idempotency, and row-level locking (`SELECT ... FOR UPDATE`). |
| **Identity & Tokens** | `djangorestframework-simplejwt` | Stateless authentication with short-lived access tokens (15m) and refresh tokens (7d). |
| **API Contract & Docs** | `drf-spectacular` (OpenAPI 3.0) | Strict schema generation directly from serializers and view contracts without manual drift. |
| **Containerization** | Docker & Docker Compose | Deterministic single-command local boot with automated migration and demo seeding. |
| **Code Quality & Tests**| `pytest`, `pytest-django`, `ruff` | Blazing-fast linting, formatting, and high-coverage automated unit, integration, and concurrency tests. |
| **Throttling / Cache** | Redis 7 (Optional) | Supportive distributed throttling and caching; never authoritative for bookings or money. |

---

## 4. Architecture Diagram

```
                                  +-----------------------+
                                  |     Client / Web      |
                                  +-----------+-----------+
                                              |
                                              | HTTPS / JSON (X-Request-ID, Bearer JWT)
                                              v
+-------------------------------------------------------------------------------------------------+
|                                 EVE Healthcare Modular Monolith                                  |
|                                                                                                 |
|   +-----------------------------------------------------------------------------------------+   |
|   | Middleware Pipeline: RequestIDMiddleware -> SecurityMiddleware -> LoggingMiddleware     |   |
|   +-----------------------------------------------------------------------------------------+   |
|                                              |                                                  |
|                                              v                                                  |
|   +-----------------------------------------------------------------------------------------+   |
|   | Thin HTTP View Layer (DRF APIViews)                                                     |   |
|   | Owns: HTTP status codes, deserialization, auth/permission checks, delegating to Service |   |
|   +-----------------------------------------------------------------------------------------+   |
|                                              |                                                  |
|                                              v                                                  |
|   +-----------------------------------------------------------------------------------------+   |
|   | Domain Service Layer                                                                    |   |
|   | Owns: Business rules, state transitions, transaction boundaries, canonical row locks    |   |
|   | [accounts.services]  [catalog.services]  [bookings.services]  [payments.services]       |   |
|   +-----------------------------------+----------------------------------+------------------+   |
|                                       |                                  |                      |
|                                       v                                  v                      |
|                   +------------------------------+     +-------------------------------+        |
|                   | Selector Layer (Read-Only)   |     | Payment Provider Abstraction  |        |
|                   | Clean, non-mutating queries  |     | [FakePaymentProvider]         |        |
|                   +--------------+---------------+     +-------------------------------+        |
|                                  |                                                              |
|                                  v                                                              |
|   +-----------------------------------------------------------------------------------------+   |
|   | Django ORM & Models                                                                     |   |
|   | User  |  DiagnosticCentre  |  DiagnosticTest  |  CentreTest  |  Booking  |  Payment     |   |
|   +-----------------------------------------------------------------------------------------+   |
+----------------------------------------------+--------------------------------------------------+
                                               |
                                               v
                        +---------------------------------------------+
                        |                PostgreSQL 16                |
                        |  - Row-Level Locking (select_for_update)    |
                        |  - Canonical Lock Order: Booking -> Payment |
                        |  - UNIQUE(idempotency_key)                  |
                        |  - UNIQUE(provider_reference)               |
                        |  - UNIQUE(event_id)                         |
                        |  - CHECK(amount > 0), CHECK(price > 0)      |
                        +---------------------------------------------+
```

---

## 5. Architectural Boundaries & Responsibility Separation

To guarantee long-term maintainability, the codebase adheres strictly to layer isolation:

1. **DRF Views**: Answer *"What HTTP request was received?"* They handle headers, authentication, request serialization, invoke exactly one domain service, and map results to HTTP status codes. Views never contain multi-step booking logic or direct state mutations.
2. **Serializers**: Answer *"Is the request/response shape valid?"* They validate data types, max lengths, email formats, and future timestamps. Serializers never decide object ownership or execute database state machine transitions.
3. **Domain Services**: Answer *"What should the business do?"* They manage transactions, row locking, ownership verification, state machine enforcement, client idempotency, and webhook verification.
4. **Selectors**: Provide read-only query helpers with zero state mutations.
5. **PostgreSQL Models**: Define database schema, foreign keys, indexes, and database-level integrity constraints (`UNIQUE`, `CHECK`).

---

## 6. Repository Layout

```
.
├── .github/workflows/ci.yml       # GitHub Actions CI pipeline
├── accounts/                      # Identity, custom User model, JWT authentication
│   ├── models.py                  # User model with UUID PK, normalized email
│   ├── serializers.py             # Signup, Login, and User serializers
│   ├── services.py                # Registration and anti-enumeration auth logic
│   ├── views.py                   # SignupView, LoginView, TokenRefreshView
│   └── urls.py
├── catalog/                       # Diagnostic centres, tests, and centre-specific pricing
│   ├── models.py                  # DiagnosticCentre, DiagnosticTest, CentreTest
│   ├── selectors.py               # Read-only centre and offering queries
│   ├── serializers.py             # Catalogue representations and creation schemas
│   ├── services.py                # Admin creation and soft-deactivation workflows
│   ├── views.py                   # Catalogue browsing, filtering, and admin endpoints
│   └── urls.py
├── bookings/                      # Appointment bookings and state machine
│   ├── models.py                  # Booking model with price snapshot, version counter
│   ├── selectors.py               # Ownership-isolated booking queries (anti-enumeration)
│   ├── serializers.py             # Booking creation and response schemas
│   ├── services.py                # Authoritative pricing snapshot, cancel, state machine
│   ├── views.py                   # Booking CRUD and cancel endpoints
│   └── urls.py
├── payments/                      # Simulated payment gateway and webhook reconciliation
│   ├── models.py                  # Payment attempt record, WebhookEvent audit ledger
│   ├── providers.py               # BasePaymentProvider, FakePaymentProvider, HMAC signer
│   ├── serializers.py             # Payment payload and webhook schemas
│   ├── services.py                # Client payment execution, HMAC verification, ledger
│   ├── views.py                   # PaymentCreateView, PaymentWebhookView
│   └── urls.py
├── common/                        # Shared cross-cutting operational utilities
│   ├── exceptions.py              # Domain exceptions and stable error codes
│   ├── handlers.py                # Global DRF exception handler (consistent error envelope)
│   ├── logging.py                 # Structured JSON log formatter
│   ├── middleware.py              # RequestIDMiddleware, StructuredLoggingMiddleware
│   ├── pagination.py              # StandardResultsSetPagination
│   ├── permissions.py             # IsAdminUserRole, IsBookingOwner
│   ├── throttling.py              # Scoped rate limiters (auth, webhook, user burst)
│   └── views.py                   # /health/live/ and /health/ready/ endpoints
├── tests/                         # Automated test suite (55 tests, 88% coverage)
│   ├── conftest.py                # Reusable fixtures and test clients
│   ├── test_auth.py               # Authentication and permission tests
│   ├── test_catalog.py            # Centre browsing and admin catalogue tests
│   ├── test_bookings.py           # Booking snapshot and ownership isolation tests
│   ├── test_payments.py           # Client payment idempotency and attempt tests
│   ├── test_webhooks.py           # HMAC signature and deduplication tests
│   ├── test_concurrency.py        # Multi-threaded PostgreSQL concurrency tests
│   └── test_operations.py         # Health probes, OpenAPI, and correlation ID tests
├── Dockerfile                     # Multi-stage Python 3.12-slim production Dockerfile
├── docker-compose.yml             # Local stack: api, postgres:16-alpine, redis:7-alpine
├── pyproject.toml                 # Package configuration, Ruff settings, Pytest options
├── requirements.txt               # Version-constrained dependencies (with minimum and compatible upper bounds)
├── .env.example                   # Annotated environment variable configuration
├── CONTEXT.md                     # Persistent architectural context document
├── ENGINEERING_JOURNAL.md         # Comprehensive chronological implementation record
└── README.md                      # This documentation
```

---

## 7. How to Run Locally

### Option A: Using Docker Compose (Recommended - Single Command)

The fastest and most reliable way to run the complete stack (API + PostgreSQL 16 + Redis) is using Docker Compose:

```bash
# 1. Clone the repository
git clone https://github.com/nimish-ratra/NimishRatra-Eve-Healthcare.git
cd NimishRatra-Eve-Healthcare

# 2. Copy the environment configuration template
cp .env.example .env

# 3. Boot the orchestrated containers
docker compose up --build
```

**What happens automatically:**
1. PostgreSQL 16 boots and initializes the `eve_healthcare_db` database.
2. The healthcheck waits until PostgreSQL is accepting connections.
3. Django applies all migrations cleanly.
4. The seeder populates deterministic demonstration data (Centres, Tests, Offerings, Admin, and Patient accounts).
5. The API server starts on `http://localhost:8000`.

### Option B: Running Bare-Metal on Local Host

If you have Python 3.12+ installed:

```bash
# 1. Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .\.venv\Scripts\Activate.ps1

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment variables (SQLite mode for instant local testing)
export USE_SQLITE="True"   # On Windows PowerShell: $env:USE_SQLITE="True"

# 4. Apply database migrations
python manage.py migrate

# 5. Populate demonstration seed data
python manage.py seed_demo_data

# 6. Start development server
python manage.py runserver 0.0.0.0:8000
```

---

## 8. Interactive API Documentation

When the application is running, open your browser:
* **Interactive Swagger UI**: [http://localhost:8000/api/docs/](http://localhost:8000/api/docs/)
* **ReDoc Interface**: [http://localhost:8000/api/redoc/](http://localhost:8000/api/redoc/)
* **Raw OpenAPI 3.0 Schema**: [http://localhost:8000/api/schema/](http://localhost:8000/api/schema/)

---

## 9. API Endpoint Specification

| Method | Endpoint | Auth Required | Scope / Purpose |
|---|---|---|---|
| `POST` | `/api/v1/auth/signup/` | Public | Register a new patient account |
| `POST` | `/api/v1/auth/login/` | Public | Authenticate and obtain JWT access & refresh tokens |
| `POST` | `/api/v1/auth/refresh/` | Refresh Token | Exchange refresh token for a new access token |
| `GET` | `/api/v1/centres/` | Public | Paginated list of active diagnostic scan centres (`?location=`) |
| `POST` | `/api/v1/centres/` | Admin | Register a new diagnostic centre |
| `POST` | `/api/v1/centres/tests/` | Admin | Register a canonical reusable diagnostic test |
| `GET` | `/api/v1/centres/{id}/tests/` | Public | List active test offerings and authoritative prices for a centre |
| `POST` | `/api/v1/centres/{id}/tests/` | Admin | Bind a diagnostic test to a centre with an authoritative price |
| `POST` | `/api/v1/bookings/` | Authenticated | Create booking and snapshot authoritative price |
| `GET` | `/api/v1/bookings/` | Authenticated | List all bookings belonging strictly to the caller |
| `GET` | `/api/v1/bookings/{id}/` | Authenticated | Retrieve booking details (ownership isolated; 404 anti-enumeration) |
| `POST` | `/api/v1/bookings/{id}/cancel/` | Authenticated | Cancel booking with PostgreSQL row lock serialization |
| `POST` | `/api/v1/payments/` | Authenticated | Initiate idempotent payment attempt (`Idempotency-Key` header) |
| `POST` | `/api/v1/payments/webhook/` | HMAC Signature | Cryptographically verified payment provider status callback |
| `GET` | `/health/live/` | Public | Process liveness probe (HTTP 200) |
| `GET` | `/health/ready/` | Public | Dependency readiness probe (HTTP 200 or 503) |

---

## 10. End-to-End Walkthrough & Example Requests

### Step 1: Patient Registration & Login

**Signup:**
```bash
curl -X POST http://localhost:8000/api/v1/auth/signup/ \
  -H "Content-Type: application/json" \
  -d '{"email": "patient@example.com", "password": "SecurePassword123!"}'
```
*Response (`HTTP 201 Created`):*
```json
{
  "id": "c1f7a01d-5a8e-4a61-827d-7bdf715b9c0a",
  "email": "patient@example.com",
  "is_admin": false,
  "created_at": "2026-09-27T12:00:00Z"
}
```

**Login:**
```bash
curl -X POST http://localhost:8000/api/v1/auth/login/ \
  -H "Content-Type: application/json" \
  -d '{"email": "patient@example.com", "password": "SecurePassword123!"}'
```
*Response (`HTTP 200 OK`):*
```json
{
  "access": "<JWT_ACCESS_TOKEN>",
  "refresh": "<JWT_REFRESH_TOKEN>",
  "user": {
    "id": "c1f7a01d-5a8e-4a61-827d-7bdf715b9c0a",
    "email": "patient@example.com",
    "is_admin": false,
    "created_at": "2026-09-27T12:00:00Z"
  }
}
```

### Step 2: Browse Catalog & Select Test Offering

```bash
# Browse centres in Gurugram
curl -X GET "http://localhost:8000/api/v1/centres/?location=Gurugram"
```
*Response excerpt:*
```json
{
  "count": 1,
  "results": [
    {
      "id": "3bb6efc8-9ff1-4560-a299-4c0388cb20c3",
      "name": "EVE Diagnostics Central - Gurugram",
      "location": "Sector 44, Gurugram, Haryana",
      "is_active": true
    }
  ]
}
```

```bash
# List available tests and prices for that centre
curl -X GET "http://localhost:8000/api/v1/centres/3bb6efc8-9ff1-4560-a299-4c0388cb20c3/tests/"
```
*Response excerpt:*
```json
{
  "count": 4,
  "results": [
    {
      "centre_test_id": "8d3e201b-9f93-4a11-8ec1-91a561bd11ef",
      "test_id": "22ff7942-ec06-4444-93ec-e81be1e843bf",
      "test_code": "MRI_BRAIN",
      "test_name": "MRI Brain with Contrast",
      "price": "3500.00"
    }
  ]
}
```

### Step 3: Book Appointment (Authoritative Pricing)

Client supplies `centre_test_id` and timezone-aware future `appointment_at`:
```bash
curl -X POST http://localhost:8000/api/v1/bookings/ \
  -H "Authorization: Bearer <JWT_ACCESS_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "centre_test_id": "8d3e201b-9f93-4a11-8ec1-91a561bd11ef",
    "appointment_at": "2026-10-15T09:30:00Z"
  }'
```
*Response (`HTTP 201 Created`):*
```json
{
  "id": "e9b4e3d1-447e-4050-9fbb-d11cfc330366",
  "user_id": "c1f7a01d-5a8e-4a61-827d-7bdf715b9c0a",
  "centre_test_id": "8d3e201b-9f93-4a11-8ec1-91a561bd11ef",
  "centre_name": "EVE Diagnostics Central - Gurugram",
  "centre_location": "Sector 44, Gurugram, Haryana",
  "test_code": "MRI_BRAIN",
  "test_name": "MRI Brain with Contrast",
  "appointment_at": "2026-10-15T09:30:00Z",
  "amount": "3500.00",
  "status": "PENDING",
  "version": 1,
  "created_at": "2026-09-27T12:05:00Z"
}
```

### Step 4: Pay for Booking (Client Idempotency)

The client passes a unique `Idempotency-Key`:
```bash
curl -X POST http://localhost:8000/api/v1/payments/ \
  -H "Authorization: Bearer <JWT_ACCESS_TOKEN>" \
  -H "Idempotency-Key: e8a7824e-b5f7-4dc4-b778-4384efcf9109" \
  -H "Content-Type: application/json" \
  -d '{
    "booking_id": "e9b4e3d1-447e-4050-9fbb-d11cfc330366"
  }'
```
*Response (`HTTP 201 Created`):*
```json
{
  "id": "73c6838a-3642-4fec-be10-8b012674eec7",
  "booking_id": "e9b4e3d1-447e-4050-9fbb-d11cfc330366",
  "idempotency_key": "e8a7824e-b5f7-4dc4-b778-4384efcf9109",
  "provider_reference": "pay_sim_91a82bc1f60e42d7",
  "amount": "3500.00",
  "status": "SUCCESS",
  "attempt_number": 1,
  "created_at": "2026-09-27T12:06:00Z"
}
```

**Retrying with the exact same key** returns `HTTP 200 OK` with the exact same payment record without invoking the provider or creating duplicate records.

---

## 11. Authoritative Pricing Model

In real-world healthcare commerce, client devices (mobile phones, web browsers) cannot be trusted to state what a service costs. If a client sends `"amount": 1.00`, a buggy or insecure server might accept it.

**In this implementation:**
1. The client selects `centre_test_id`.
2. The server loads the `CentreTest` record.
3. The server verifies that the offering is active, the centre is active, and the diagnostic test is active.
4. The server extracts `CentreTest.price`.
5. The server stores that value in `Booking.amount`.
6. Even if a client sends an `amount` field in the payload, it is strictly ignored.
7. `Booking.amount` becomes an **immutable snapshot**. If scan centre fees change tomorrow, historical bookings retain the original agreed price.

---

## 12. Booking Finite State Machine

All status mutations must pass through the centralized `BookingStateMachine` inside `bookings/services.py`:

```
                    +--------------------+
                    |      PENDING       |
                    +---+--------+---+---+
                        |        |   |
      Payment FAILED    |        |   | Payment SUCCESS
            +-----------+        |   +------------+
            |                    |                |
            v                    | User cancels   v
     +--------------+            |         +--------------+
     |    FAILED    |            +-------->|  CANCELLED   |
     +------+-------+                      +-------+------+
            |                                      |
            | Retry with new                       | Terminal State
            | successful payment attempt           | (Never Resurrected!)
            v                                      |
     +--------------+                              v
     |  CONFIRMED   +------------------------------+
     +--------------+         User cancels
```

### Transition Invariants
- `PENDING` $\rightarrow$ `CONFIRMED` (On successful payment attempt or webhook)
- `PENDING` $\rightarrow$ `FAILED` (On declined payment attempt or failure webhook)
- `PENDING` $\rightarrow$ `CANCELLED` (On patient cancellation)
- `FAILED` $\rightarrow$ `CONFIRMED` (Allowed when a new retry payment attempt succeeds)
- `CONFIRMED` $\rightarrow$ `CANCELLED` (Allowed under cancellation policy)
- `CANCELLED` $\rightarrow$ Any (Forbidden! Cancelled bookings are never resurrected by late-arriving webhooks or retry attempts)

---

## 13. Concurrency Serialization & Canonical Lock Order

### The Race Condition Problem
Consider a patient clicking "Cancel Appointment" on their phone at the exact same millisecond that a payment webhook arrives from the gateway stating "Payment Successful".
If both transactions execute concurrently without locking, one could confirm while the other cancels, resulting in contradictory database state or unrecorded refunds.

### The Solution: PostgreSQL Row Locks & Canonical Ordering
1. PostgreSQL row locks (`SELECT ... FOR UPDATE`) serialize concurrent transactions at the database boundary.
2. **Canonical Lock Order**: Whenever an operation requires locking both a Booking and a Payment row, it **must** acquire them in this strict order:
   $$\text{Booking} \longrightarrow \text{Payment}$$
   Acquiring locks in inconsistent orders (e.g. Path A: Booking then Payment; Path B: Payment then Booking) causes database **deadlocks**. This system uses canonical ordering universally across all code paths.
3. **Re-Read After Lock**: A service never relies on an in-memory object fetched prior to acquiring the lock. Once `select_for_update()` is granted, the committed status is re-read from PostgreSQL before applying the state transition.
4. **Short Lock Windows**: External network calls to payment providers are **never** executed while holding database row locks. The intent is persisted, transaction committed, provider invoked outside the lock, and the result settled in a follow-up transaction.

---

## 14. Webhook Cryptographic Security & Deduplication

Webhooks from external providers arrive over the public Internet. The webhook endpoint (`POST /api/v1/payments/webhook/`) implements strict defensive measures:

1. **Raw Body Inspection**: The cryptographic signature is computed over the raw incoming request bytes (`request.body`). Re-serializing parsed JSON can alter whitespace and property ordering, breaking signature verification.
2. **Timestamp Freshness**: The `X-Webhook-Timestamp` header is verified against a 300-second freshness window, defeating capture-and-replay attacks.
3. **HMAC-SHA256 Verification**:
   $$\text{HMAC-SHA256}(\text{Secret},\; \text{Timestamp} + "." + \text{RawBody})$$
4. **Constant-Time Comparison**: `hmac.compare_digest()` is used to prevent byte-by-byte timing attacks.
5. **Parse Only After Authenticity**: Untrusted JSON is parsed only after the cryptographic signature passes.
6. **Savepoint-Isolated Event Ledger**: Webhook event IDs are inserted into `webhook_events` (`UNIQUE(event_id)`). To prevent PostgreSQL transaction invalidation on unique collisions within `transaction.atomic()`, duplicate detection uses nested atomic savepoints. Duplicates return `HTTP 200 OK` acknowledged without side effects.

---

## 15. Unified Error Handling & Machine-Readable Error Codes

All domain errors return a predictable JSON envelope with a correlation request ID:

```json
{
  "error": {
    "code": "BOOKING_NOT_FOUND",
    "message": "Booking does not exist or is not accessible to this user.",
    "details": {},
    "request_id": "a4d8c792-7f28-4e89-b1d5-ec54199c0e2a"
  }
}
```

| Stable Error Code | HTTP Status | Meaning |
|---|---|---|
| `BOOKING_NOT_FOUND` | 404 | Booking does not exist or belongs to another patient (anti-enumeration) |
| `BOOKING_CANCELLED` | 409 | Attempted action invalid on a cancelled booking |
| `BOOKING_NOT_PENDING` | 409 | Operation requires PENDING status |
| `OFFERING_UNAVAILABLE` | 409 | Diagnostic offering or scan centre is inactive |
| `IDEMPOTENCY_KEY_REUSED`| 409 | Same idempotency key was reused for a different booking |
| `WEBHOOK_SIGNATURE_INVALID` | 401 | HMAC-SHA256 signature is missing or incorrect |
| `WEBHOOK_TIMESTAMP_STALE` | 401 | Webhook timestamp falls outside freshness window |
| `WEBHOOK_EVENT_DUPLICATE` | 200 | Event already processed; duplicate safely acknowledged |
| `AMOUNT_MISMATCH` | 409 | Webhook amount does not match authoritative booking snapshot |

---

## 16. Operational Health Probes

- **`/health/live/` (Process Liveness)**: Returns `HTTP 200 {"status": "alive"}`. Validates that the Python web worker is responsive. Does *not* query the database so a momentary PostgreSQL failover does not trigger container restarts.
- **`/health/ready/` (Dependency Readiness)**: Returns `HTTP 200 {"status": "ready", "database": "connected"}` or `HTTP 503`. Executes `SELECT 1;` on PostgreSQL. Directs load balancers to halt incoming user traffic when the database is unavailable.

---

## 17. Automated Testing Suite

The repository contains **55 comprehensive automated tests** achieving **88% code coverage**.

### Test Execution Commands

```bash
# Run the entire test suite with coverage report
pytest --cov=. --cov-report=term-missing

# Run authentication and authorization tests
pytest tests/test_auth.py -v

# Run catalog and pricing tests
pytest tests/test_catalog.py -v

# Run booking lifecycle and snapshot tests
pytest tests/test_bookings.py -v

# Run payment idempotency and attempt tests
pytest tests/test_payments.py -v

# Run HMAC webhook verification tests
pytest tests/test_webhooks.py -v

# Run concurrency and race condition tests
pytest tests/test_concurrency.py -v

# Run code style and lint checks with Ruff
ruff check .
ruff format --check .
```

### PostgreSQL Concurrency Testing
While unit tests use SQLite for rapid execution, concurrency-critical tests (`tests/test_concurrency.py`) test multi-threaded row locking, transaction boundaries, and uniqueness collisions. The GitHub Actions CI pipeline provisions a real PostgreSQL 16 container service to prove row-level lock serialization under true database conditions.

---

## 18. Architectural Assumptions & Explicit Boundaries

1. **Simulated Payment Gateway**: No real bank or credit card integration is included. Payment interactions are handled through a deterministic `FakePaymentProvider`.
2. **Authoritative Centre-Specific Pricing**: Medical test definitions are reusable; prices are specific to individual scan centers via `CentreTest`.
3. **No Capacity Engine**: The assignment specification does not define calendar slot capacity or machine availability; bookings do not enforce inventory limits.
4. **Soft Deactivation**: Historical diagnostic offerings and centres are soft-deactivated (`is_active = False`) rather than deleted, preserving clinical audit integrity.
5. **Redis is Non-Authoritative**: Redis is optionally used for distributed throttling and cache; PostgreSQL remains the sole source of truth for all financial transactions and booking states.
6. **No Asynchronous Job Overhead**: Celery was deliberately omitted because booking and payment correctness are synchronous domain requirements. Asynchronous outbox processing is documented below as a future evolution.

---

## 19. Production Evolution & Future Roadmap

For scaling into a nationwide healthcare platform:
1. **Transactional Outbox Pattern**: Emit booking events into an `outbox_events` table within the same PostgreSQL transaction, with a background worker relaying messages to Apache Kafka or RabbitMQ for patient SMS and email dispatch.
2. **Provider Reconciliation Jobs**: Scheduled nightly cron worker to fetch settled transaction batches from gateway APIs and reconcile discrepancies with local payment records.
3. **Slot Capacity Management**: Introduce `Slot` models with resource limits per scan room (e.g. MRI 1.5T scanner) to prevent overbooking physical diagnostic equipment.
4. **Automated Refund Workflows**: If a confirmed booking is cancelled, trigger an automated refund intent through the payment provider adapter.
