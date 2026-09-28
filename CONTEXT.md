# EVE Healthcare - Diagnostic Booking & Payments Backend
## System Context & Final Architectural Blueprint

*Last updated: Final Verification Completed - 100% Pass Rate across 55 Tests (88% Coverage)*

---

### 1. Final Project Overview
The EVE Healthcare Diagnostic Booking & Payments API is a production-grade backend monolith implementing diagnostic test discovery, authoritative price snapshotting, patient appointment bookings, simulated payments with client idempotency, and cryptographically verified webhook event reconciliation.

All critical correctness guarantees survive network retries, duplicate webhook delivery, concurrent requests, catalogue price fluctuations, and unauthorized access attempts.

---

### 2. Assignment Requirements & Implementation Mapping

| Assignment Requirement | Architectural Implementation | Verification |
|---|---|---|
| **User Authentication** | Custom UUID `User` model, normalized email identity, Argon2/PBKDF2 hashing, SimpleJWT access/refresh tokens. | `tests/test_auth.py` (10 tests) |
| **Diagnostic Centres & Tests** | `DiagnosticCentre`, `DiagnosticTest`, and `CentreTest` pricing mapping. Location filtering, pagination, admin permissions. | `tests/test_catalog.py` (9 tests) |
| **Booking System** | Authoritative price resolution and snapshotting into `Booking.amount`. Timezone-aware future scheduling. | `tests/test_bookings.py` (9 tests) |
| **Ownership Isolation** | Scoped queries by `booking_id` + `request.user`. Anti-enumeration returns 404 for other patients' records. | `tests/test_bookings.py` |
| **Booking State Machine** | Centralized finite state machine: `PENDING`, `CONFIRMED`, `FAILED`, `CANCELLED`. Resurrections strictly prevented. | `tests/test_bookings.py` |
| **Simulated Payments** | Provider abstraction `BasePaymentProvider` with deterministic `FakePaymentProvider`. Attempt numbering. | `tests/test_payments.py` (7 tests) |
| **Payment Idempotency** | Client `Idempotency-Key` header with database `UNIQUE(idempotency_key)`. Inner savepoint isolates `IntegrityError` so concurrent same-key requests safely replay without transaction abortion; different booking returns 409. | `tests/test_payments.py`, `tests/test_concurrency.py` |
| **Webhook Ingestion** | Raw body HMAC-SHA256 verification, 300s timestamp freshness window, constant-time compare before JSON parsing. | `tests/test_webhooks.py` (9 tests) |
| **Webhook Idempotency** | Savepoint-isolated atomic ledger `UNIQUE(event_id)`. Duplicate returns 200 acknowledged without side effects. | `tests/test_webhooks.py` |
| **Concurrency Protection** | Canonical row locking (`Booking -> Payment`), re-read after lock, zero locks held during external provider calls. | `tests/test_concurrency.py` (4 tests) |
| **Observability & Health** | `X-Request-ID` correlation middleware, privacy-safe JSON logging, split `/health/live/` and `/health/ready/`. | `tests/test_operations.py` (7 tests) |
| **API Documentation** | `drf-spectacular` generating complete OpenAPI 3.0 specification, Swagger UI (`/api/docs/`), ReDoc (`/api/redoc/`). | Validated with 0 warnings |
| **Containerization & CI** | Production multi-stage `Dockerfile`, environment-driven `docker-compose.yml`, GitHub Actions workflow with Postgres 16. | Full CI workflow ready |

---

### 3. Frozen Technology Stack
* **Runtime**: Python 3.12+
* **Framework**: Django 5.x / Django REST Framework
* **Database**: PostgreSQL 16 (authoritative transactional store and row-level locking)
* **Authentication**: `djangorestframework-simplejwt`
* **API Documentation**: `drf-spectacular`
* **Containerization**: Docker Compose (environment-driven configuration)
* **Quality Tooling**: `pytest`, `pytest-django`, `pytest-cov`, `ruff`
* **Cache & Throttling**: Redis 7 (supportive infrastructure; never authoritative)

---

### 4. Domain Models & Database Invariants

```
accounts.User (Table: users)
├── id: UUIDField (PK)
├── email: EmailField (UNIQUE, normalized lowercase, indexed)
├── password: PasswordHash (never serialized)
├── is_active: BooleanField (default=True)
└── is_admin: BooleanField (default=False)

catalog.DiagnosticCentre (Table: diagnostic_centres)
├── id: UUIDField (PK)
├── name: CharField(255)
├── location: CharField(255, indexed)
└── is_active: BooleanField (soft deactivation)

catalog.DiagnosticTest (Table: diagnostic_tests)
├── id: UUIDField (PK)
├── code: CharField(50, UNIQUE, indexed)
├── name: CharField(255)
└── is_active: BooleanField (soft deactivation)

catalog.CentreTest (Table: centre_tests)
├── id: UUIDField (PK)
├── centre: FK(DiagnosticCentre, PROTECT)
├── test: FK(DiagnosticTest, PROTECT)
├── price: DecimalField(10,2) (CHECK: price > 0)
└── Invariant: UNIQUE(centre, test)

bookings.Booking (Table: bookings)
├── id: UUIDField (PK)
├── user: FK(User, PROTECT, indexed)
├── centre_test: FK(CentreTest, PROTECT)
├── appointment_at: DateTimeField (future, timezone-aware)
├── amount: DecimalField(10,2) (Authoritative price snapshot, CHECK: amount > 0)
├── status: CharField(20, choices=[PENDING, CONFIRMED, FAILED, CANCELLED])
├── version: PositiveIntegerField (default=1, incremented on each transition)
└── Indexes: (user, -created_at), (appointment_at, status)

payments.Payment (Table: payments)
├── id: UUIDField (PK)
├── booking: FK(Booking, PROTECT, indexed)
├── idempotency_key: CharField(255, UNIQUE)
├── provider_reference: CharField(255, UNIQUE)
├── amount: DecimalField(10,2) (CHECK: amount > 0)
├── status: CharField(20, choices=[INITIATED, SUCCESS, FAILED])
├── attempt_number: PositiveIntegerField (default=1)
└── Invariants: UNIQUE(idempotency_key), UNIQUE(provider_reference), UNIQUE(booking, attempt_number)

payments.WebhookEvent (Table: webhook_events)
├── id: UUIDField (PK)
├── event_id: CharField(255, UNIQUE, indexed)
├── provider_reference: CharField(255, indexed)
├── payload_hash: CharField(64)
├── received_at: DateTimeField(auto_now_add=True)
└── processed_at: DateTimeField(null=True)
```

---

### 5. Architectural Invariants That Must NOT Be Changed

1. **Authoritative Pricing**: The client *never* specifies the price of a booking. Price is looked up from `CentreTest` server-side and snapshotted into `Booking.amount`.
2. **Canonical Lock Ordering**: Any routine locking both `Booking` and `Payment` **must** lock in the strict order: `Booking` then `Payment`. Never invert this ordering.
3. **Re-Read After Lock**: Always re-fetch and inspect the committed row status *after* acquiring a `select_for_update()` lock before making transition decisions.
4. **Short Database Lock Duration**: Payment provider calls are executed *outside* database row locks. Intent is persisted, transaction committed, provider invoked, and state settled in a subsequent transaction.
5. **HMAC Verification Order**: Always check raw request bytes + timestamp freshness *before* parsing the JSON body.
6. **Savepoint-Isolated Payment & Webhook Operations**: Database writes that can encounter unique constraint collisions under concurrency (`Payment` idempotency key and `WebhookEvent` event ID) use nested atomic savepoints (`with transaction.atomic():`) so that collisions do not abort the outer transaction block.
7. **No Cancellation Resurrections**: Once a booking reaches `CANCELLED`, it can never transition to any other status. Late webhooks and payment attempts are safely ignored or rejected.
8. **Anti-Enumeration Ownership**: Bookings are queried by `id=booking_id, user=request.user`. Bookings belonging to another user return `HTTP 404 Not Found` (`BOOKING_NOT_FOUND`).

---

### 6. Verification Status

- **Automated Tests**: 55 passed (0 failed, 0 skipped) in 15.97s.
- **Code Coverage**: 88% overall statement coverage across all domain modules.
- **Linter & Formatter**: Ruff check passed with 0 errors; all files formatted.
- **Django Migrations**: Clean schema history, zero uncommitted or pending model changes.
- **OpenAPI Schema**: Validated via `drf-spectacular --validate --fail-on-warn` with 0 errors and 0 warnings.
- **Demonstration Seeding**: Deterministic seed command (`python manage.py seed_demo_data`) populates accounts, centres, and offerings.

---

### 7. How to Continue for Future Developers

```bash
# 1. Activate environment
source .venv/bin/activate  # or Windows PowerShell: .\.venv\Scripts\Activate.ps1

# 2. Run test suite
pytest --cov=. --cov-report=term-missing

# 3. Start local development server
python manage.py runserver

# 4. Or boot with Docker Compose
docker compose up --build
```
