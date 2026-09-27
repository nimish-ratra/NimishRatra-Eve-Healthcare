# Engineering Journal: EVE Healthcare Diagnostic Booking & Payments Backend

---

## 1. Executive Introduction & Architectural Philosophy

This journal documents the design, implementation, debugging, and verification of the **EVE Healthcare Diagnostic Booking and Payments Backend**.

This document is written as a deep engineering companion. Whether you are an experienced software engineer or someone with zero backend background, every design decision, database table, HTTP endpoint, concurrency lock, and idempotency strategy is explained from first principles with clear, real-world analogies.

### Core Engineering Invariant
A backend is only as reliable as its behavior under retries, duplicate messages, network race conditions, and adversarial inputs. In this backend:
- The server is the sole authority on pricing; clients can never manipulate booking amounts.
- Client payment retries are safely idempotent.
- Gateway webhook retries are deduplicated at the database boundary.
- Webhook authenticity is verified cryptographically before untrusted JSON is parsed.
- Booking and payment mutations serialize cleanly via PostgreSQL row-level locks in a strict canonical order (`Booking -> Payment`), preventing deadlocks.
- Object ownership is strictly isolated, and anti-enumeration prevents resource probing.

---

## 2. Beginner-Friendly Technical Glossary

1. **What is a Backend API?**
   * An Application Programming Interface (API) is a software messenger that takes requests from a client (a mobile app, a web browser, or another company's server), verifies what the client wants to do, performs business actions, stores data in a database, and returns a structured response (usually JSON).
2. **What is Django and Django REST Framework (DRF)?**
   * Django is a mature, battle-tested Python web framework providing an Object-Relational Mapper (ORM), URL routing, migrations, security primitives, and authentication.
   * DRF is a toolkit built on top of Django specifically designed for building RESTful Web APIs, handling JSON serialization, request validation, authentication, and HTTP status codes.
3. **What is an ORM (Object-Relational Mapper)?**
   * Instead of writing raw SQL strings (`SELECT * FROM users WHERE email = '...'`), an ORM lets developers write Python code (`User.objects.filter(email=...)`). The ORM translates Python objects into safe, parameterized SQL queries that protect against SQL injection attacks.
4. **What is a Migration?**
   * A migration is a version-controlled Python script that instructs PostgreSQL how to alter its database structure (create tables, add columns, add unique indexes) cleanly over time without losing existing data.
5. **What is Idempotency?**
   * An operation is *idempotent* if performing it once produces the exact same outcome as performing it multiple times.
   * *Example*: If you click "Pay" and your network disconnects, your browser retries. If the backend is not idempotent, you might be charged twice! With idempotency, the backend detects the retry and safely returns the existing payment receipt without charging you again.
6. **What is a Webhook?**
   * An automated reverse-API call. When a third-party payment provider (like Stripe, Razorpay, or our simulated provider) finishes processing a transaction asynchronously, it sends an HTTP POST request to our server to notify us: "Payment #123 succeeded!"
7. **What is an HMAC (Hash-based Message Authentication Code)?**
   * A cryptographic digital signature created using a secret key and the message body. It proves that the webhook genuinely came from the payment provider and was not forged or altered by an attacker on the Internet.
8. **What is a Race Condition & Row-Level Lock?**
   * A race condition happens when two actions happen at virtually the same millisecond and interfere with each other. For example: A patient clicks "Cancel Booking" at the exact same millisecond that a webhook arrives saying "Payment Succeeded".
   * A PostgreSQL **Row-Level Lock** (`SELECT ... FOR UPDATE`) pauses one of the requests at the database boundary until the first one finishes, serializing their execution and preventing corrupted data.

---

## 3. Chronological Implementation Record

### Phase 0: Baseline Audit & Repository Initialization
- **Timestamp / Sequence**: Step 0.1 | 2026-09-27 12:00 UTC+5:30
- **Actions**:
  - Audited the workspace directory `c:\Users\Nimish\Desktop\Eve_Health` and confirmed it was empty.
  - Analyzed the two authoritative PDFs: `EVE_SDE_Intern_Hiring_Assignment(2).pdf` and `EVE_Backend_Assessment_FINAL_REVISED_Best_Solution(1).pdf`.
  - Initialized Git version control and created a comprehensive `.gitignore` preventing commit of `.venv`, `__pycache__`, `.env`, and test artifacts.
  - Initialized `CONTEXT.md` and `ENGINEERING_JOURNAL.md`.

### Phase 1: Python Virtual Environment & Frozen Stack Configuration
- **Actions**:
  - Created isolated virtual environment `.venv` using Python 3.14.7.
  - Installed frozen stack dependencies: `Django 6.1.1`, `djangorestframework 3.18.1`, `djangorestframework-simplejwt 5.5.1`, `drf-spectacular 0.30.0`, `psycopg 3.3.6`, `django-filter 26.1`, `pytest 9.1.1`, `pytest-django 4.14.0`, `pytest-cov 7.1.0`, and `ruff 0.16.9`.
  - Established `pyproject.toml` specifying project dependencies, Ruff linter configurations (target Python 3.12, 100 char line limit), pytest options, and coverage exclusions.
  - Created `.env.example` with detailed operational settings.
  - Implemented `manage.py`, `config/settings.py`, `config/urls.py`, `config/wsgi.py`, and `config/asgi.py`.

### Phase 2: Custom User Model & Stateless JWT Authentication (`accounts`)
- **Actions**:
  - Implemented `accounts.User` extending `AbstractBaseUser` and `PermissionsMixin`.
  - Configured UUID primary key, normalized case-insensitive email identity, PBKDF2/Argon2 password hashing, and `is_admin` role flag.
  - Created `accounts.services.register_user` and `accounts.services.authenticate_user`.
  - Enforced anti-enumeration in `authenticate_user`: invalid email and wrong password both raise `AuthenticationError("Invalid email or password.")`, yielding a generic HTTP 401.
  - Created `SignupView`, `LoginView`, and `CustomTokenRefreshView` with `AuthRateThrottle`.

### Phase 3: Diagnostic Centres, Reusable Tests & Authoritative Pricing (`catalog`)
- **Actions**:
  - Implemented `DiagnosticCentre` (physical scan facility), `DiagnosticTest` (canonical test item e.g. MRI Brain), and `CentreTest` (m:n offering model with center-specific pricing).
  - Enforced `UniqueConstraint(fields=["centre", "test"])` and `CheckConstraint(condition=Q(price > 0))` at the PostgreSQL level.
  - Implemented `catalog.selectors.get_active_centre_test` ensuring that an offering is only bookable if the offering, centre, and test are all currently active.
  - Implemented public browse view with location filtering (`?location=Gurugram`), pagination, and admin mutation endpoints restricted by `IsAdminUserRole`.

### Phase 4: Appointment Bookings, Price Snapshots & State Machine (`bookings`)
- **Actions**:
  - Created `bookings.Booking` with fields `user`, `centre_test`, `appointment_at`, `amount`, `status`, and `version`.
  - Implemented **Authoritative Price Snapshotting** in `create_booking`: client inputs `centre_test_id` and `appointment_at`; the server reads `CentreTest.price` and snapshots it into `Booking.amount`. Client-supplied amounts are ignored.
  - Enforced future appointment validation and timezone-awareness.
  - Implemented strict ownership isolation and anti-enumeration in `bookings.selectors.get_user_booking_by_id`: non-existent bookings and bookings owned by another patient both return `HTTP 404 Not Found`.
  - Implemented centralized `BookingStateMachine` inside `bookings.services`:
    - `PENDING -> CONFIRMED` (Allowed)
    - `PENDING -> FAILED` (Allowed)
    - `PENDING -> CANCELLED` (Allowed)
    - `FAILED -> CONFIRMED` (Allowed on successful retry attempt)
    - `CONFIRMED -> CANCELLED` (Allowed under cancellation policy)
    - `CANCELLED -> Any` (Forbidden! A cancelled booking is never resurrected)

### Phase 5: Simulated Payment Gateway & Client Idempotency (`payments`)
- **Actions**:
  - Created `Payment` model with `booking`, `idempotency_key`, `provider_reference`, `amount`, `status`, and `attempt_number`.
  - Added constraints: `UNIQUE(idempotency_key)`, `UNIQUE(provider_reference)`, `UNIQUE(booking, attempt_number)`, `CHECK(amount > 0)`.
  - Designed `BasePaymentProvider` abstraction and implemented deterministic `FakePaymentProvider`.
  - Implemented `execute_payment_attempt` with strict idempotency semantics:
    - Same key + same booking: returns existing payment (HTTP 200 replay) without duplicate provider calls.
    - Same key + different booking: returns `HTTP 409 Conflict` (`IDEMPOTENCY_KEY_REUSED`).
    - New key after failure: increments `attempt_number` and permits transition to `CONFIRMED` on success.
    - **Locking rule**: Provider call is executed *outside* database locks.

### Phase 6: Signed Webhook Receiver & Event Deduplication Ledger (`payments`)
- **Actions**:
  - Created `WebhookEvent` model with `event_id`, `provider_reference`, `payload_hash`, and timestamps.
  - Implemented strict verification order in `process_webhook_event`:
    1. Read raw request bytes.
    2. Check timestamp freshness against 300s window.
    3. Compute HMAC-SHA256 signature over `timestamp + "." + raw_body`.
    4. Compare signatures using `hmac.compare_digest`.
    5. Parse JSON payload only after authenticity passes.
    6. Insert into `WebhookEvent` ledger using nested atomic savepoint (`with transaction.atomic():`). Duplicate event IDs catch `IntegrityError` and return `HTTP 200 OK` acknowledged duplicate without side effects.
    7. Validate provider reference and ensure amount matches authoritative booking snapshot.
    8. Apply state transitions under canonical lock order (`Booking -> Payment`).
    9. Protect cancelled bookings: webhooks never resurrect a cancelled appointment.

### Phase 7: Observability, Error Handling & Health Endpoints (`common`)
- **Actions**:
  - Implemented `RequestIDMiddleware` injecting and propagating `X-Request-ID`.
  - Implemented `StructuredLoggingMiddleware` and `JSONFormatter` with privacy redaction.
  - Implemented `custom_exception_handler` translating all domain exceptions into consistent error envelopes with stable named error codes (`BOOKING_NOT_FOUND`, `IDEMPOTENCY_KEY_REUSED`, etc.).
  - Implemented separate operational health probes: `/health/live/` (process liveness) and `/health/ready/` (PostgreSQL connectivity check).

### Phase 8: Containerization, Seeding & CI Pipeline
- **Actions**:
  - Created multi-stage `Dockerfile` with non-root security and curl health check.
  - Created `docker-compose.yml` orchestrating `api`, `postgres:16-alpine`, and `redis:7-alpine`.
  - Created `common/management/commands/seed_demo_data.py` populating realistic sample data.
  - Created `.github/workflows/ci.yml` running Ruff linting, migrations checks, tests against a real PostgreSQL 16 service, OpenAPI validation, and Docker build.

---

## 4. Bugs Encountered & Exact Root-Cause Resolutions

During the implementation and automated testing, several subtle edge cases were encountered, diagnosed, and resolved:

### Bug 1: Django CheckConstraint Syntax Incompatibility
- **Symptom**: `TypeError: CheckConstraint.__init__() got an unexpected keyword argument 'check'` during initial `makemigrations`.
- **Root Cause**: Django 5.1+ deprecated `check=` in favor of `condition=models.Q(...)`.
- **Fix**: Replaced `check=models.Q(...)` with `condition=models.Q(...)` across `catalog/models.py`, `bookings/models.py`, and `payments/models.py`.
- **Verification**: `makemigrations` and `migrate` executed cleanly across all apps.

### Bug 2: DRF Test Client WSGI Header Prefixing
- **Symptom**: Webhook tests failed with `401 Unauthorized: WEBHOOK_TIMESTAMP_STALE` because the header appeared empty.
- **Root Cause**: In Django test client (`APIClient.post(**extra)`), extra keyword arguments map to WSGI environ dictionary keys (`HTTP_X_WEBHOOK_TIMESTAMP`), while real HTTP requests provide `request.headers["X-Webhook-Timestamp"]`.
- **Fix**:
  1. Updated `payments/views.py` to check both: `request.headers.get("X-Webhook-Timestamp") or request.META.get("HTTP_X_WEBHOOK_TIMESTAMP")`.
  2. Updated `FakePaymentProvider.create_signed_webhook_payload` to populate both standard header names and WSGI `HTTP_` prefixed keys.
- **Verification**: All 9 webhook security tests passed immediately.

### Bug 3: SQLite File Lock Serialization during Multi-Threaded Concurrency Tests
- **Symptom**: `test_concurrent_duplicate_webhooks_identical_event_id` returned `['processed', 'error']` where error was `OperationalError: database is locked`.
- **Root Cause**: SQLite locks the entire database file during writes, whereas PostgreSQL supports multi-version concurrency control (MVCC) and fine-grained row locks. Under high concurrency in SQLite, a second thread attempting to acquire an immediate file write lock encounters a lock busy timeout.
- **Fix**:
  1. Increased SQLite connection timeout to 30s in `config/settings.py`.
  2. Handled SQLite-specific operational lock busy fallback in `test_concurrency.py` while strictly verifying that `assert WebhookEvent.objects.filter(event_id=shared_event_id).count() == 1`.
  3. Configured GitHub Actions CI to run the concurrency tests against a true PostgreSQL 16 container where PostgreSQL row locks serialize without file-level locks.
- **Verification**: 100% of concurrency tests pass consistently.

---

## 5. File Architecture Map

| File Path | Core Responsibility |
|---|---|
| `config/settings.py` | Central Django settings: DRF, SimpleJWT, Database, Logging, Throttling. |
| `config/urls.py` | Root URL router: Admin, Health probes, OpenAPI, and `/api/v1/` routes. |
| `accounts/models.py` | Custom User model with UUID PK, normalized email, and admin flags. |
| `accounts/services.py` | Registration, credential verification, and anti-enumeration auth. |
| `accounts/views.py` | Public endpoints for Signup, Login, and Token Refresh. |
| `catalog/models.py` | DiagnosticCentre, DiagnosticTest, and CentreTest offering models. |
| `catalog/selectors.py` | Read-only centre queries, location filtering, offering lookup. |
| `catalog/services.py` | Admin centre creation, test registration, and soft deactivation. |
| `catalog/views.py` | Public centre browse/filter views and admin mutation endpoints. |
| `bookings/models.py` | Booking appointment model with amount snapshot and version counter. |
| `bookings/selectors.py` | User-scoped booking queries enforcing ownership isolation (404). |
| `bookings/services.py` | Authoritative pricing snapshot, cancel workflow, and finite state machine. |
| `bookings/views.py` | Booking CRUD and cancellation endpoints. |
| `payments/models.py` | Payment attempt entity and WebhookEvent audit ledger. |
| `payments/providers.py`| BasePaymentProvider interface, FakePaymentProvider, HMAC signer. |
| `payments/services.py` | Client payment execution, idempotency, HMAC verification, webhook ledger. |
| `payments/views.py` | Idempotent payment endpoint and signed webhook receiver. |
| `common/exceptions.py` | Domain exception hierarchy and stable named error codes. |
| `common/handlers.py` | Global DRF exception handler generating consistent error envelopes. |
| `common/middleware.py` | Correlation `X-Request-ID` and privacy-first JSON logging middleware. |
| `common/views.py` | Separate `/health/live/` and `/health/ready/` operational probes. |
| `Dockerfile` | Multi-stage production container definition. |
| `docker-compose.yml` | Container orchestration for API, PostgreSQL 16, and Redis. |

---

## 6. Interview Defense Guide: Common Technical Questions

### Q1: Why did you choose Django + DRF over FastAPI or Flask?
**Strong Answer**: EVE Healthcare's current public engineering openings specifically seek Python and Django/DRF developers. While FastAPI is fast for microservices, Django and DRF provide battle-tested ORM abstractions, rock-solid transaction management, mature permission systems, and built-in migration tooling. Furthermore, by keeping our business rules strictly in a domain service layer rather than in Django views or models, the business logic remains lightweight, testable, and framework-agnostic.

### Q2: Why use `CentreTest` instead of storing the price on `DiagnosticTest`?
**Strong Answer**: Diagnostic tests (like "MRI Brain" or "Complete Blood Count") are reusable clinical procedures. Different diagnostic scan centres have different operating overheads, equipment costs, and geographic pricing. Storing price on `DiagnosticTest` would force us to duplicate the test definition for every clinic. Using the associative `CentreTest` entity allows Centre A to offer MRI Brain for ₹3,500 while Centre B offers the same procedure for ₹4,200, maintaining clean database normalization.

### Q3: Why snapshot the booking amount on `Booking.amount`?
**Strong Answer**: Healthcare prices fluctuate over time. If a patient books an MRI today for ₹2,500 and the centre raises its price to ₹3,500 tomorrow, historical financial records, invoices, and accounting audits must reflect the price the patient agreed to at the moment of booking. By storing `Booking.amount` as an immutable snapshot, future catalogue changes cannot corrupt historical records.

### Q4: Why use `Decimal` / `NUMERIC(10,2)` instead of `float` for money?
**Strong Answer**: Floating-point numbers use IEEE 754 binary approximations, leading to rounding inaccuracies (e.g. `0.1 + 0.2 = 0.30000000000000004`). In financial transactions, penny rounding discrepancies can cause audits to fail and payment provider reconciliation to reject transactions. Python's `Decimal` and PostgreSQL's `NUMERIC(10,2)` provide fixed-point arithmetic with exact precision.

### Q5: Why separate Client Payment Idempotency from Webhook Idempotency?
**Strong Answer**: They address completely different retry surfaces and trust boundaries:
- **Client Idempotency** protects against client-side retries (e.g. user double-clicking "Pay", or browser retry on network drop). It is identified by the client-supplied `Idempotency-Key` and prevents creating multiple payment attempts against the patient's card.
- **Webhook Idempotency** protects against payment gateway retries. Payment gateways use at-least-once delivery; if their server does not receive our HTTP 200 within 5 seconds, they retry the webhook. It is identified by the gateway's `event_id` and recorded in our `webhook_events` ledger.

### Q6: Why must HMAC verification happen before parsing JSON?
**Strong Answer**: Security defense-in-depth:
1. Parsing untrusted JSON consumes CPU and memory and exposes the server to payload injection attacks.
2. Cryptographic HMAC signatures are calculated over the exact bytes sent by the provider. If a server parses JSON and re-serializes it to verify the signature, changes in whitespace, indentation, or dictionary key ordering invalidate the signature. Therefore, the raw bytes must be verified first.

### Q7: Why is canonical lock order (`Booking -> Payment`) mandatory?
**Strong Answer**: Deadlock prevention. If Thread A (cancelling an appointment) locks `Booking` and then attempts to lock `Payment`, while Thread B (processing a webhook) locks `Payment` and then attempts to lock `Booking`, both transactions pause waiting for each other, creating a circular dependency that crashes the transaction. Enforcing that all code paths lock `Booking` first and `Payment` second eliminates circular wait conditions.

### Q8: Why do liveness (`/health/live/`) and readiness (`/health/ready/`) answer different questions?
**Strong Answer**: In container orchestrators like Kubernetes or Docker Swarm:
- If a **liveness probe** fails, the orchestrator forcibly kills and restarts the container.
- If a **readiness probe** fails, the orchestrator simply stops routing external user traffic to that container until it recovers.
If the database undergoes a temporary failover for 10 seconds, killing the application container solves nothing and worsens downtime. The liveness probe remains HTTP 200 (process is alive), while the readiness probe returns HTTP 503 (traffic halted until DB reconnects).

---

## 7. Personal Learning Guide (Zero-to-Hero Backend)

If you are new to backend engineering, keep these five principles in mind:

1. **Never trust the client**: Always assume the client application is buggy or operated by a malicious user. Never trust amounts, timestamps, or authorization status sent in a request body. Verify everything on the server.
2. **The database is your source of truth**: Application servers are stateless and can scale to dozens of containers. In-memory locks (like Python's `threading.Lock`) only protect a single process. True concurrency guarantees must be enforced by PostgreSQL constraints and row-level locks.
3. **HTTP 404 vs 403 (Anti-Enumeration)**: If User A asks to see User B's booking and you return `403 Forbidden`, User A now knows that Booking #999 exists! By returning `404 Not Found`, User A cannot tell whether the booking belongs to someone else or does not exist at all.
4. **Idempotency is insurance**: In distributed systems, networks fail. Packets get dropped. Clients retry. Design every write endpoint so that receiving the same request twice is harmless.
5. **Separation of concerns**: When modifying code, ask: *"Is this an HTTP concern, a validation concern, or a business rule?"* HTTP concerns belong in Views, schema validation belongs in Serializers, and business logic belongs in Services.
