"""
Payment Domain Services:
Encapsulates client payment execution, idempotency resolution,
strict HMAC webhook verification, and database-enforced event deduplication.
"""

import hashlib
import hmac
import json
import logging
import time
import uuid

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from bookings.models import Booking, BookingStatus
from bookings.services import BookingStateMachine
from common.exceptions import (
    BookingCancelledError,
    BookingNotFoundError,
    IdempotencyKeyReusedError,
    InvalidPaymentStateError,
    PaymentAmountMismatchError,
    ProviderReferenceNotFoundError,
    WebhookEventDuplicateError,
    WebhookSignatureInvalidError,
    WebhookTimestampStaleError,
)
from payments.models import Payment, PaymentStatus, WebhookEvent
from payments.providers import BasePaymentProvider, FakePaymentProvider
from payments.serializers import WebhookPayloadSerializer

logger = logging.getLogger("eve_healthcare.payments")


def execute_payment_attempt(
    user,
    booking_id: uuid.UUID,
    idempotency_key: str,
    simulate_failure: bool = False,
    provider: BasePaymentProvider | None = None,
) -> tuple[Payment, bool]:
    """Processes a client-initiated payment attempt with strict idempotency and lock boundaries.

    Returns:
        (payment, created) -> created is True for a new charge attempt, False for an idempotent replay.
    """
    if provider is None:
        provider = FakePaymentProvider()

    clean_key = idempotency_key.strip()

    # Step 1: Client Idempotency Pre-check
    existing_payment = Payment.objects.filter(idempotency_key=clean_key).first()
    if existing_payment:
        if existing_payment.booking_id == booking_id:
            # Same idempotency key + same booking: safe replay of existing outcome
            logger.info(
                f"Idempotent payment replay for booking {booking_id} with key '{clean_key}'"
            )
            return existing_payment, False
        else:
            # Same idempotency key + different booking: 409 Conflict
            logger.warning(
                f"Idempotency key reuse conflict! Key '{clean_key}' already used for booking {existing_payment.booking_id}, "
                f"attempted for booking {booking_id}"
            )
            raise IdempotencyKeyReusedError(
                "This idempotency key has already been used for a different booking."
            )

    # Step 2: Validate Booking and initialize Attempt under row lock
    is_idempotent_replay = False
    with transaction.atomic():
        try:
            # Canonical lock order: Lock Booking first
            booking = (
                Booking.objects.select_for_update()
                .select_related("user")
                .get(id=booking_id, user=user)
            )
        except (Booking.DoesNotExist, ValueError) as err:
            raise BookingNotFoundError(
                "Booking does not exist or is not accessible to this user."
            ) from err

        if booking.status == BookingStatus.CANCELLED:
            raise BookingCancelledError("Payment attempted on a cancelled booking.")

        if booking.status == BookingStatus.CONFIRMED:
            raise InvalidPaymentStateError("This booking has already been paid and confirmed.")

        # Determine attempt number
        attempt_number = Payment.objects.filter(booking=booking).count() + 1

        temp_provider_ref = f"init_{uuid.uuid4().hex[:16]}"
        try:
            # P0 Invariant: Inner savepoint isolates IntegrityError so the outer transaction remains valid
            with transaction.atomic():
                payment = Payment.objects.create(
                    booking=booking,
                    idempotency_key=clean_key,
                    provider_reference=temp_provider_ref,
                    amount=booking.amount,
                    status=PaymentStatus.INITIATED,
                    attempt_number=attempt_number,
                )
        except IntegrityError as exc:
            # Inner savepoint rolled back cleanly. The outer transaction can safely execute queries.
            existing = Payment.objects.filter(idempotency_key=clean_key).first()
            if existing:
                if existing.booking_id == booking_id:
                    # Scenario 1: Same key + same booking -> safe replay of existing intent
                    logger.info(
                        f"Concurrent race safely resolved: key '{clean_key}' reuses existing payment {existing.id}."
                    )
                    payment = existing
                    is_idempotent_replay = True
                else:
                    # Scenario 2: Same key + different booking -> 409 Conflict
                    logger.warning(
                        f"Idempotency collision under concurrency: key '{clean_key}' used for booking {existing.booking_id}, "
                        f"attempted for {booking_id}."
                    )
                    raise IdempotencyKeyReusedError(
                        "This idempotency key has already been used for a different booking."
                    ) from exc
            else:
                raise IdempotencyKeyReusedError(
                    "Payment creation failed due to unique constraint collision under concurrency."
                ) from exc

    # If this request was a concurrent duplicate that replayed an existing payment,
    # skip external provider invocation and return the existing payment immediately.
    if is_idempotent_replay:
        return payment, False

    # Step 3: Invoke simulated payment gateway OUTSIDE of database row locks
    # In production, external network latency would block other database transactions.
    provider_result = provider.process_payment(
        amount=booking.amount,
        booking_id=str(booking.id),
        simulate_failure=simulate_failure,
    )

    # Step 4: Reconcile result inside a new transaction with canonical lock ordering
    with transaction.atomic():
        # Canonical lock order: 1. Booking, 2. Payment
        booking = Booking.objects.select_for_update().get(id=booking_id)
        payment = Payment.objects.select_for_update().get(id=payment.id)

        # Update provider reference to the authoritative value from the gateway
        payment.provider_reference = provider_result.provider_reference

        if booking.status == BookingStatus.CANCELLED:
            # If user cancelled while provider was processing, do NOT resurrect!
            payment.status = PaymentStatus.FAILED
            payment.save(update_fields=["status", "provider_reference", "updated_at"])
            logger.warning(
                f"Payment {payment.id} completed after booking {booking.id} was cancelled. Marking payment failed."
            )
            return payment, True

        if provider_result.success:
            payment.status = PaymentStatus.SUCCESS
            BookingStateMachine.apply_transition(booking, BookingStatus.CONFIRMED)
        else:
            payment.status = PaymentStatus.FAILED
            BookingStateMachine.apply_transition(booking, BookingStatus.FAILED)

        payment.save(update_fields=["status", "provider_reference", "updated_at"])

    return payment, True


def verify_webhook_signature(
    raw_body: bytes,
    timestamp_header: str | None,
    signature_header: str | None,
) -> None:
    """Verifies HMAC-SHA256 signature and timestamp freshness before payload parsing.

    Verification Order:
    1. Check presence and validity of timestamp.
    2. Check timestamp freshness against tolerance window.
    3. Check presence of signature.
    4. Compute expected HMAC: HMAC(secret, timestamp + '.' + raw_body).
    5. Constant-time comparison using hmac.compare_digest.
    """
    if not timestamp_header:
        raise WebhookTimestampStaleError("Missing X-Webhook-Timestamp header.")

    try:
        req_timestamp = int(timestamp_header)
    except (ValueError, TypeError) as err:
        raise WebhookTimestampStaleError("Invalid X-Webhook-Timestamp header format.") from err

    current_time = int(time.time())
    tolerance = settings.WEBHOOK_TIMESTAMP_TOLERANCE_SECONDS
    if abs(current_time - req_timestamp) > tolerance:
        raise WebhookTimestampStaleError("Webhook timestamp falls outside freshness window.")

    if not signature_header:
        raise WebhookSignatureInvalidError("Missing X-Webhook-Signature header.")

    secret = settings.WEBHOOK_SECRET
    signature_base = f"{req_timestamp}.".encode() + raw_body
    expected_sig = hmac.new(
        secret.encode("utf-8"),
        signature_base,
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(expected_sig, signature_header):
        raise WebhookSignatureInvalidError("Webhook signature mismatch.")


def process_webhook_event(
    raw_body: bytes,
    timestamp_header: str | None,
    signature_header: str | None,
) -> dict:
    """Processes an incoming payment webhook callback with strict security and idempotency.

    Key Reliability Invariant:
    - IntegrityError on UNIQUE(event_id) is isolated using an inner savepoint (nested transaction.atomic)
      so that duplicate events do not invalidate outer transaction state.
    """
    # 1. Cryptographic Authentication & Freshness
    verify_webhook_signature(raw_body, timestamp_header, signature_header)

    # 2. Schema Validation (only parsed AFTER signature authenticity verified)
    try:
        payload_data = json.loads(raw_body.decode("utf-8"))
    except json.JSONDecodeError as err:
        raise WebhookSignatureInvalidError("Webhook body could not be decoded as JSON.") from err

    serializer = WebhookPayloadSerializer(data=payload_data)
    serializer.is_valid(raise_exception=True)
    validated = serializer.validated_data

    event_id = validated["event_id"]
    event_type = validated["event_type"]
    provider_ref = validated["provider_reference"]
    amount = validated["amount"]

    payload_hash = hashlib.sha256(raw_body).hexdigest()

    # 3. Database-Enforced Idempotency Ledger with Savepoint Isolation
    # Use nested atomic block to prevent IntegrityError from spoiling any outer transaction
    try:
        with transaction.atomic():
            webhook_event = WebhookEvent.objects.create(
                event_id=event_id,
                provider_reference=provider_ref,
                payload_hash=payload_hash,
            )
    except IntegrityError as err:
        logger.info(f"Duplicate webhook event '{event_id}' safely acknowledged.")
        raise WebhookEventDuplicateError(
            f"Webhook event '{event_id}' has already been processed."
        ) from err

    # 4. Resolve Payment Record by provider reference
    payment = (
        Payment.objects.select_related("booking").filter(provider_reference=provider_ref).first()
    )
    if not payment:
        logger.warning(f"Webhook received for unknown provider reference: {provider_ref}")
        raise ProviderReferenceNotFoundError(
            f"No payment record found for provider reference '{provider_ref}'."
        )

    # 5. Authoritative Amount Validation
    if payment.amount != amount:
        logger.error(
            f"Webhook amount mismatch for payment {payment.id}: expected {payment.amount}, received {amount}"
        )
        raise PaymentAmountMismatchError(
            f"Webhook amount ₹{amount} does not match expected payment amount ₹{payment.amount}."
        )

    # 6. Apply State Machine Transitions under Canonical Lock Order (Booking -> Payment)
    with transaction.atomic():
        # Canonical order: 1. Booking
        booking = Booking.objects.select_for_update().get(id=payment.booking_id)
        # Canonical order: 2. Payment
        payment_locked = Payment.objects.select_for_update().get(id=payment.id)

        # Re-check current committed status after acquiring locks
        if booking.status == BookingStatus.CANCELLED:
            # Policy invariant: Never resurrect a cancelled booking
            logger.info(f"Webhook ignored for cancelled booking {booking.id} (Event: {event_id})")
            webhook_event.processed_at = timezone.now()
            webhook_event.save(update_fields=["processed_at"])
            return {
                "status": "ignored",
                "reason": "booking_cancelled",
                "event_id": event_id,
            }

        if event_type == "payment.success":
            if payment_locked.status == PaymentStatus.SUCCESS:
                # Already settled; safe no-op
                pass
            else:
                payment_locked.status = PaymentStatus.SUCCESS
                payment_locked.save(update_fields=["status", "updated_at"])
                BookingStateMachine.apply_transition(booking, BookingStatus.CONFIRMED)

        elif event_type == "payment.failed":
            if booking.status == BookingStatus.CONFIRMED:
                # Late arriving failure must not regress an already confirmed booking
                logger.warning(
                    f"Ignored late payment.failed webhook for already confirmed booking {booking.id}"
                )
            else:
                payment_locked.status = PaymentStatus.FAILED
                payment_locked.save(update_fields=["status", "updated_at"])
                BookingStateMachine.apply_transition(booking, BookingStatus.FAILED)

        webhook_event.processed_at = timezone.now()
        webhook_event.save(update_fields=["processed_at"])

    return {
        "status": "processed",
        "event_id": event_id,
        "booking_status": booking.status,
    }
