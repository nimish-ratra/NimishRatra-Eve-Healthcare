"""
Payment Webhook & Cryptographic Verification Integration Tests:
Tests HMAC-SHA256 signature verification, timestamp freshness, duplicate event deduplication,
amount validation, and prevention of state corruption / cancelled booking resurrection.
"""

import time
import uuid
from decimal import Decimal

import pytest
from django.conf import settings
from django.urls import reverse
from rest_framework import status

from bookings.models import BookingStatus
from payments.models import Payment, PaymentStatus, WebhookEvent


@pytest.fixture
def sample_payment(db, pending_booking):
    """Initial payment attempt tied to pending_booking."""
    return Payment.objects.create(
        booking=pending_booking,
        idempotency_key=f"idem_{uuid.uuid4()}",
        provider_reference=f"pay_prov_{uuid.uuid4().hex[:12]}",
        amount=pending_booking.amount,
        status=PaymentStatus.INITIATED,
        attempt_number=1,
    )


@pytest.mark.django_db
class TestPaymentWebhooks:
    def test_valid_success_webhook_confirms_booking(
        self, api_client, sample_payment, pending_booking, webhook_signer
    ):
        event_id = f"evt_{uuid.uuid4()}"
        raw_body, headers = webhook_signer(
            event_id=event_id,
            provider_reference=sample_payment.provider_reference,
            event_type="payment.success",
            amount=sample_payment.amount,
            secret=settings.WEBHOOK_SECRET,
        )

        url = reverse("payment-webhook")
        response = api_client.post(url, data=raw_body, content_type="application/json", **headers)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["status"] == "processed"

        sample_payment.refresh_from_db()
        assert sample_payment.status == PaymentStatus.SUCCESS

        pending_booking.refresh_from_db()
        assert pending_booking.status == BookingStatus.CONFIRMED

        # Assert recorded in WebhookEvent idempotency ledger
        assert WebhookEvent.objects.filter(event_id=event_id).exists()

    def test_missing_signature_rejected_401(self, api_client, sample_payment, webhook_signer):
        raw_body, headers = webhook_signer(
            event_id=f"evt_{uuid.uuid4()}",
            provider_reference=sample_payment.provider_reference,
            event_type="payment.success",
            amount=sample_payment.amount,
            secret=settings.WEBHOOK_SECRET,
        )
        headers.pop("X-Webhook-Signature", None)
        headers.pop("HTTP_X_WEBHOOK_SIGNATURE", None)

        url = reverse("payment-webhook")
        response = api_client.post(url, data=raw_body, content_type="application/json", **headers)

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert response.data["error"]["code"] == "WEBHOOK_SIGNATURE_INVALID"

    def test_invalid_signature_rejected_401(self, api_client, sample_payment, webhook_signer):
        raw_body, headers = webhook_signer(
            event_id=f"evt_{uuid.uuid4()}",
            provider_reference=sample_payment.provider_reference,
            event_type="payment.success",
            amount=sample_payment.amount,
            secret=settings.WEBHOOK_SECRET,
        )
        headers["X-Webhook-Signature"] = "bad_signature_deadbeef"
        headers["HTTP_X_WEBHOOK_SIGNATURE"] = "bad_signature_deadbeef"

        url = reverse("payment-webhook")
        response = api_client.post(url, data=raw_body, content_type="application/json", **headers)

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert response.data["error"]["code"] == "WEBHOOK_SIGNATURE_INVALID"

    def test_stale_timestamp_rejected_401(self, api_client, sample_payment, webhook_signer):
        # Timestamp from 10 minutes ago (exceeds 300s tolerance)
        stale_time = int(time.time()) - 600
        raw_body, headers = webhook_signer(
            event_id=f"evt_{uuid.uuid4()}",
            provider_reference=sample_payment.provider_reference,
            event_type="payment.success",
            amount=sample_payment.amount,
            secret=settings.WEBHOOK_SECRET,
            timestamp=stale_time,
        )

        url = reverse("payment-webhook")
        response = api_client.post(url, data=raw_body, content_type="application/json", **headers)

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert response.data["error"]["code"] == "WEBHOOK_TIMESTAMP_STALE"

    def test_duplicate_webhook_acknowledged_200_without_side_effects(
        self, api_client, sample_payment, pending_booking, webhook_signer
    ):
        event_id = f"evt_dup_{uuid.uuid4()}"
        raw_body, headers = webhook_signer(
            event_id=event_id,
            provider_reference=sample_payment.provider_reference,
            event_type="payment.success",
            amount=sample_payment.amount,
            secret=settings.WEBHOOK_SECRET,
        )

        url = reverse("payment-webhook")
        # 1. First delivery
        resp1 = api_client.post(url, data=raw_body, content_type="application/json", **headers)
        assert resp1.status_code == status.HTTP_200_OK
        assert resp1.data["status"] == "processed"

        # 2. Duplicate delivery with identical event_id
        resp2 = api_client.post(url, data=raw_body, content_type="application/json", **headers)
        assert resp2.status_code == status.HTTP_200_OK
        assert resp2.data["status"] == "acknowledged"
        assert resp2.data["code"] == "WEBHOOK_EVENT_DUPLICATE"

        # Assert only 1 ledger entry exists
        assert WebhookEvent.objects.filter(event_id=event_id).count() == 1

    def test_unknown_provider_reference_rejected_404(self, api_client, webhook_signer):
        raw_body, headers = webhook_signer(
            event_id=f"evt_{uuid.uuid4()}",
            provider_reference="unknown_provider_ref_999",
            event_type="payment.success",
            amount=Decimal("2500.00"),
            secret=settings.WEBHOOK_SECRET,
        )

        url = reverse("payment-webhook")
        response = api_client.post(url, data=raw_body, content_type="application/json", **headers)

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert response.data["error"]["code"] == "PROVIDER_REFERENCE_NOT_FOUND"

    def test_amount_mismatch_rejected_409(self, api_client, sample_payment, webhook_signer):
        raw_body, headers = webhook_signer(
            event_id=f"evt_{uuid.uuid4()}",
            provider_reference=sample_payment.provider_reference,
            event_type="payment.success",
            amount=Decimal("9999.00"),  # Mismatch from booking amount 2500.00
            secret=settings.WEBHOOK_SECRET,
        )

        url = reverse("payment-webhook")
        response = api_client.post(url, data=raw_body, content_type="application/json", **headers)

        assert response.status_code == status.HTTP_409_CONFLICT
        assert response.data["error"]["code"] == "AMOUNT_MISMATCH"

    def test_webhook_for_cancelled_booking_does_not_resurrect(
        self, api_client, sample_payment, pending_booking, webhook_signer
    ):
        # Cancel booking first
        pending_booking.status = BookingStatus.CANCELLED
        pending_booking.save()

        raw_body, headers = webhook_signer(
            event_id=f"evt_cancel_{uuid.uuid4()}",
            provider_reference=sample_payment.provider_reference,
            event_type="payment.success",
            amount=sample_payment.amount,
            secret=settings.WEBHOOK_SECRET,
        )

        url = reverse("payment-webhook")
        response = api_client.post(url, data=raw_body, content_type="application/json", **headers)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["status"] == "ignored"

        pending_booking.refresh_from_db()
        # Non-negotiable invariant: CANCELLED booking is NEVER resurrected!
        assert pending_booking.status == BookingStatus.CANCELLED

    def test_late_failed_webhook_does_not_regress_confirmed_booking(
        self, api_client, sample_payment, pending_booking, webhook_signer
    ):
        # Booking and payment already confirmed and successful
        pending_booking.status = BookingStatus.CONFIRMED
        pending_booking.save()
        sample_payment.status = PaymentStatus.SUCCESS
        sample_payment.save()

        # Out-of-order late webhook reporting failure arrives
        raw_body, headers = webhook_signer(
            event_id=f"evt_late_fail_{uuid.uuid4()}",
            provider_reference=sample_payment.provider_reference,
            event_type="payment.failed",
            amount=sample_payment.amount,
            secret=settings.WEBHOOK_SECRET,
        )

        url = reverse("payment-webhook")
        response = api_client.post(url, data=raw_body, content_type="application/json", **headers)

        assert response.status_code == status.HTTP_200_OK

        pending_booking.refresh_from_db()
        assert pending_booking.status == BookingStatus.CONFIRMED
        sample_payment.refresh_from_db()
        assert sample_payment.status == PaymentStatus.SUCCESS
