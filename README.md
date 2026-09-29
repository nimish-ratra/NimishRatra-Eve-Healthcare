# EVE Healthcare - Diagnostic Booking & Payments Backend API

Assessment-focused backend service for the EVE Healthcare SDE Intern Backend Assessment, implementing diagnostic scan centre discovery, authoritative price snapshotting, patient appointment scheduling, simulated payments with client idempotency, and cryptographically authenticated webhook reconciliation.

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
- **Observability & Diagnostics**: Request/correlation ID injection (`X-Request-ID`), privacy-first structured JSON logging (no PII or credentials logged), split liveness (`/health/live/`) and readiness (`/health/ready/`) probes.
- **API Documentation**: Automated OpenAPI 3.0 specification with interactive Swagger UI and ReDoc interfaces generated via `drf-spectacular`.

---

## 3. Technology Stack & Architectural Decisions

| Layer / Concern | Chosen Technology | Justification |
|---|---|---|
| **Language & Runtime** | Python 3.12+ | Clean, readable syntax, standard type hints, and robust async/synchronous ecosystem. |
| **Framework** | Django (>=5.1, <6.2; tested with 6.1.1) + DRF | Aligns directly with EVE Healthcare's technology stack. Provides battle-tested serializers, security middleware, and ORM abstractions. |
| **Primary Database** | PostgreSQL 16 | ACID transactions, exact NUMERIC currency storage, unique indexes for idempotency, and row-level locking (`SELECT ... FOR UPDATE`). |
| **Identity & Tokens** | `djangorestframework-simplejwt` | Stateless authentication with short-lived access tokens (15m) and refresh tokens (7d). |
| **API Contract & Docs** | `drf-spectacular` (OpenAPI 3.0) | Strict schema generation directly from serializers and view contracts without manual drift. |
| **Containerization** | Docker & Docker Compose | Deterministic single-command local boot with automated migration and demo seeding. |
| **Code Quality & Tests**| `pytest`, `pytest-django`, `pytest-cov`, `ruff` | Fast linting, formatting, and high-coverage automated unit, integration, and concurrency tests. |
| **Throttling Policies** | Django REST Framework Throttling | Scoped in-memory rate limiters for auth endpoints and webhook burst protection. |

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

## 5. Architectural Boundaries & Layer Isolation

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
├── .github/workflows/ci.yml       # GitHub Actions CI pipeline (PostgreSQL 16, lint, test, docker)
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
├── Dockerfile                     # Container definition based on python:3.12-slim
├── docker-compose.yml             # Local stack: api, postgres:16-alpine
├── pyproject.toml                 # Package configuration, Ruff settings, Pytest options
├── requirements.txt               # Version-constrained dependencies
├── .env.example                   # Annotated environment variable configuration template
└── README.md                      # Evaluation and setup documentation
```

---

## 7. How to Run Locally

### Option A: Using Docker Compose (Primary & Recommended)

The primary evaluation method is Docker Compose, which boots PostgreSQL 16 and the Django API:

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
1. PostgreSQL 16 starts and initializes the `eve_healthcare_db` database.
2. The healthcheck confirms PostgreSQL is accepting connections.
3. The Django container connects to PostgreSQL using the Docker network service name (`DB_HOST=db`).
4. Django applies database migrations cleanly.
5. The seeder populates deterministic demonstration data (Centres, Tests, Offerings, Admin, and Patient accounts).
6. The API server starts on `http://localhost:8000`.

### Option B: Running Bare-Metal on Local Host

If you have Python 3.12+ installed locally:

```bash
# 1. Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows PowerShell: .\.venv\Scripts\Activate.ps1

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment variables
# For lightweight local testing without a local PostgreSQL instance:
export USE_SQLITE="True"   # On Windows PowerShell: $env:USE_SQLITE="True"

# Note: If connecting to a local PostgreSQL server directly on your host machine:
# export DB_HOST="localhost"
# export USE_SQLITE="False"

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

---

### Step 2: Browse Diagnostic Centres & Test Offerings

**List Centres (Filtered by Location):**
```bash
curl -X GET "http://localhost:8000/api/v1/centres/?location=Gurugram"
```

**List Centre Tests & Authoritative Prices:**
```bash
curl -X GET "http://localhost:8000/api/v1/centres/<CENTRE_UUID>/tests/"
```

---

### Step 3: Create Booking (Authoritative Pricing Snapshot)

The client supplies only the offering identifier and desired appointment time. The server resolves the price and snapshots it into the booking record.

```bash
curl -X POST http://localhost:8000/api/v1/bookings/ \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <JWT_ACCESS_TOKEN>" \
  -d '{
    "centre_test_id": "<CENTRE_TEST_UUID>",
    "appointment_at": "2026-10-15T09:30:00Z"
  }'
```
*Response (`HTTP 201 Created`):*
```json
{
  "id": "3f9e8a71-6c24-4d89-b821-4f108269e8b1",
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

---

### Step 4: Pay for Booking (Client Idempotency)

Supply a unique `Idempotency-Key` header. If the network drops and the client repeats the request with the identical key, the server safely returns the original payment attempt without initiating a duplicate charge.

```bash
curl -X POST http://localhost:8000/api/v1/payments/ \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <JWT_ACCESS_TOKEN>" \
  -H "Idempotency-Key: client_req_uuid_999a8b" \
  -d '{
    "booking_id": "3f9e8a71-6c24-4d89-b821-4f108269e8b1"
  }'
```
*Response (`HTTP 201 Created` on first call; `HTTP 200 OK` on idempotent retry):*
```json
{
  "id": "7a8b9c0d-1e2f-3a4b-5c6d-7e8f9a0b1c2d",
  "booking_id": "3f9e8a71-6c24-4d89-b821-4f108269e8b1",
  "idempotency_key": "client_req_uuid_999a8b",
  "provider_reference": "sim_prov_a8f9301b",
  "amount": "3500.00",
  "status": "SUCCESS",
  "attempt_number": 1,
  "created_at": "2026-09-27T12:06:00Z",
  "updated_at": "2026-09-27T12:06:01Z"
}
```

---

### Step 5: Webhook Status Callback (Signed HMAC-SHA256)

When an asynchronous payment gateway updates payment status, it delivers a signed webhook to `POST /api/v1/payments/webhook/`.

```bash
# Headers:
# X-Webhook-Timestamp: 1758974760
# X-Webhook-Signature: <hex_digest of HMAC-SHA256(secret, timestamp + "." + raw_body)>
curl -X POST http://localhost:8000/api/v1/payments/webhook/ \
  -H "Content-Type: application/json" \
  -H "X-Webhook-Timestamp: 1758974760" \
  -H "X-Webhook-Signature: a9f8e7d6c5b4..." \
  -d '{
    "event_id": "evt_gateway_987654",
    "event_type": "payment.success",
    "provider_reference": "sim_prov_a8f9301b",
    "amount": "3500.00",
    "timestamp": 1758974760
  }'
```
*Response (`HTTP 200 OK`):*
```json
{
  "status": "processed",
  "event_id": "evt_gateway_987654",
  "booking_status": "CONFIRMED"
}
```

---

## 11. Core Domain Models & Invariants

```
                +-------------------------+
                |     DiagnosticCentre    |
                +-------------------------+
                | name: CharField         |
                | location: CharField     |
                | is_active: BooleanField |
                +------------+------------+
                             | 1
                             | offers
                             | N
                +------------v------------+              +-------------------------+
                |       CentreTest        |   for test   |      DiagnosticTest     |
                +-------------------------+------------->+-------------------------+
                | centre: FK(Centre)      | N          1 | code: CharField (UNIQUE)|
                | test: FK(Test)          |              | name: CharField         |
                | price: Decimal(10,2)    |              | is_active: BooleanField |
                | UNIQUE(centre, test)    |              +-------------------------+
                | CHECK(price > 0)        |
                +------------+------------+
                             | 1
                             | booked in
                             | N
                +------------v------------+
                |         Booking         |
                +-------------------------+
                | user: FK(User)          |
                | centre_test: FK         |
                | appointment_at: DateTime|
                | amount: Decimal(10,2)   | <--- Immutable snapshot from CentreTest
                | status: BookingStatus   |      [PENDING, CONFIRMED, FAILED, CANCELLED]
                | version: Integer        | <--- Optimistic concurrency counter
                | CHECK(amount > 0)       |
                +------------+------------+
                             | 1
                             | paid via
                             | N
                +------------v------------+              +-------------------------+
                |         Payment         |              |       WebhookEvent      |
                +-------------------------+              +-------------------------+
                | booking: FK(Booking)    |              | event_id: Char (UNIQUE) |
                | idempotency_key: UNIQUE |              | provider_reference: Char|
                | provider_reference: UNIQ|              | payload_hash: Char(64)  |
                | amount: Decimal(10,2)   |              | processed_at: DateTime  |
                | status: PaymentStatus   |              +-------------------------+
                | attempt_number: Integer |
                | UNIQUE(booking, attempt)|
                | CHECK(amount > 0)       |
                +-------------------------+
```

---

## 12. Finite State Machine & Lifecycle Rules

All booking status transitions are mediated by the centralized `BookingStateMachine` in `bookings/services.py`:

```
                       +-----------------------+
                       |        PENDING        |
                       +-----------+-----------+
                                   |
         +-------------------------+-------------------------+
         | (Payment Success)       | (Payment Failed)        | (User Cancels)
         v                         v                         v
+-----------------+       +-----------------+       +-----------------+
|    CONFIRMED    |       |     FAILED      |       |    CANCELLED    |
+--------+--------+       +--------+--------+       +-----------------+
         |                         |                         ^
         | (User Cancels)          | (Retry Payment Success) | (User Cancels)
         v                         +-------------------------+
+-----------------+                |
|    CANCELLED    |                v
+-----------------+       +-----------------+
                          |    CONFIRMED    |
                          +-----------------+
```

### Transition Invariants
- `PENDING` $\rightarrow$ `CONFIRMED` (On successful payment attempt or webhook)
- `PENDING` $\rightarrow$ `FAILED` (On declined payment attempt or failure webhook)
- `PENDING` $\rightarrow$ `CANCELLED` (On patient cancellation)
- `FAILED` $\rightarrow$ `CONFIRMED` (Allowed when a new retry payment attempt succeeds)
- `FAILED` $\rightarrow$ `CANCELLED` (Allowed if patient cancels after failure)
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
   Acquiring locks in inconsistent orders causes database **deadlocks**. This system uses canonical ordering universally across all code paths.
3. **Re-Read After Lock**: A service never relies on an in-memory object fetched prior to acquiring the lock. Once `select_for_update()` is granted, the committed status is re-read from PostgreSQL before applying the state transition.
4. **Short Lock Windows**: External network calls to payment providers are **never** executed while holding database row locks. The intent is persisted, transaction committed, provider invoked outside the lock, and the result settled in a follow-up transaction.
5. **Invariant**: No invalid, contradictory, or impossible state transition occurs. The race results in a valid final state according to the state machine (CONFIRMED or CANCELLED, never PENDING, never corrupted, and cancelled bookings are never resurrected).

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
5. **In-Memory Rate Limiting**: Scoped throttling policies (for authentication and webhooks) leverage Django REST Framework's built-in in-memory throttle caches. PostgreSQL remains the sole source of truth for all bookings and payments.
6. **No Asynchronous Job Overhead**: Celery was deliberately omitted because booking and payment correctness are synchronous domain requirements. Asynchronous outbox processing is documented below as a future evolution.

---

## 19. Production Evolution & Future Roadmap

For scaling into a nationwide healthcare platform:
1. **Transactional Outbox Pattern**: Emit booking events into an `outbox_events` table within the same PostgreSQL transaction, with a background worker relaying messages to Apache Kafka or RabbitMQ for patient SMS and email dispatch.
2. **Provider Reconciliation Jobs**: Scheduled nightly cron worker to fetch settled transaction batches from gateway APIs and reconcile discrepancies with local payment records.
3. **Slot Capacity Management**: Introduce `Slot` models with resource limits per scan room (e.g. MRI 1.5T scanner) to prevent overbooking physical diagnostic equipment.
4. **Automated Refund Workflows**: If a confirmed booking is cancelled, trigger an automated refund intent through the payment provider adapter.
