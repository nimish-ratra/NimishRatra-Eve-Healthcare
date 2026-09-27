"""
Client Payment & Idempotency Integration Tests:
Tests payment success/failure, client idempotency replays, key conflict on different bookings,
attempt numbering, retry after failure, and rejection of non-payable states.
"""

import uuid
from decimal import Decimal

import pytest
from django.urls import reverse
from rest_framework import status

from bookings.models import BookingStatus
from payments.models import Payment, PaymentStatus


@pytest.mark.django_db
class TestPayments:
    def test_payment_success_transitions_booking_to_confirmed(
        self, api_client, auth_headers_patient, pending_booking
    ):
        url = reverse("payment-create")
        idempotency_key = f"key_{uuid.uuid4()}"
        headers = {**auth_headers_patient, "HTTP_IDEMPOTENCY_KEY": idempotency_key}

        payload = {"booking_id": str(pending_booking.id)}
        response = api_client.post(url, payload, format="json", **headers)

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["status"] == PaymentStatus.SUCCESS
        assert response.data["attempt_number"] == 1
        assert Decimal(response.data["amount"]) == pending_booking.amount

        pending_booking.refresh_from_db()
        assert pending_booking.status == BookingStatus.CONFIRMED
        assert pending_booking.version == 2

    def test_payment_failure_simulation(self, api_client, auth_headers_patient, pending_booking):
        url = reverse("payment-create")
        idempotency_key = f"key_{uuid.uuid4()}"
        headers = {**auth_headers_patient, "HTTP_IDEMPOTENCY_KEY": idempotency_key}

        payload = {"booking_id": str(pending_booking.id), "simulate_failure": True}
        response = api_client.post(url, payload, format="json", **headers)

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["status"] == PaymentStatus.FAILED

        pending_booking.refresh_from_db()
        assert pending_booking.status == BookingStatus.FAILED

    def test_same_idempotency_key_same_booking_replays_original_result(
        self, api_client, auth_headers_patient, pending_booking
    ):
        url = reverse("payment-create")
        idempotency_key = f"key_replay_{uuid.uuid4()}"
        headers = {**auth_headers_patient, "HTTP_IDEMPOTENCY_KEY": idempotency_key}
        payload = {"booking_id": str(pending_booking.id)}

        # 1. First attempt: returns 201 Created
        resp1 = api_client.post(url, payload, format="json", **headers)
        assert resp1.status_code == status.HTTP_201_CREATED
        original_payment_id = resp1.data["id"]

        # 2. Retry with identical idempotency key: returns 200 OK replay
        resp2 = api_client.post(url, payload, format="json", **headers)
        assert resp2.status_code == status.HTTP_200_OK
        assert resp2.data["id"] == original_payment_id

        # Assert no duplicate payment attempts were created in DB
        assert Payment.objects.filter(booking=pending_booking).count() == 1

    def test_same_idempotency_key_different_booking_rejected_409(
        self, api_client, auth_headers_patient, pending_booking, centre_test_offering, patient_user
    ):
        from django.utils import timezone

        second_booking = pending_booking.__class__.objects.create(
            user=patient_user,
            centre_test=centre_test_offering,
            appointment_at=timezone.now() + timezone.timedelta(days=4),
            amount=centre_test_offering.price,
            status=BookingStatus.PENDING,
        )

        url = reverse("payment-create")
        shared_key = f"key_conflict_{uuid.uuid4()}"

        # 1. First booking uses key
        headers1 = {**auth_headers_patient, "HTTP_IDEMPOTENCY_KEY": shared_key}
        resp1 = api_client.post(
            url, {"booking_id": str(pending_booking.id)}, format="json", **headers1
        )
        assert resp1.status_code == status.HTTP_201_CREATED

        # 2. Second booking attempts to reuse the same key
        headers2 = {**auth_headers_patient, "HTTP_IDEMPOTENCY_KEY": shared_key}
        resp2 = api_client.post(
            url, {"booking_id": str(second_booking.id)}, format="json", **headers2
        )
        assert resp2.status_code == status.HTTP_409_CONFLICT
        assert resp2.data["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"

    def test_retry_after_failed_creates_new_attempt_and_confirms(
        self, api_client, auth_headers_patient, pending_booking
    ):
        url = reverse("payment-create")

        # 1. Attempt 1: Failed
        key1 = f"key_attempt_1_{uuid.uuid4()}"
        resp1 = api_client.post(
            url,
            {"booking_id": str(pending_booking.id), "simulate_failure": True},
            format="json",
            **{**auth_headers_patient, "HTTP_IDEMPOTENCY_KEY": key1},
        )
        assert resp1.status_code == status.HTTP_201_CREATED
        assert resp1.data["status"] == PaymentStatus.FAILED
        assert resp1.data["attempt_number"] == 1

        pending_booking.refresh_from_db()
        assert pending_booking.status == BookingStatus.FAILED

        # 2. Attempt 2 with NEW idempotency key: Success
        key2 = f"key_attempt_2_{uuid.uuid4()}"
        resp2 = api_client.post(
            url,
            {"booking_id": str(pending_booking.id), "simulate_failure": False},
            format="json",
            **{**auth_headers_patient, "HTTP_IDEMPOTENCY_KEY": key2},
        )
        assert resp2.status_code == status.HTTP_201_CREATED
        assert resp2.data["status"] == PaymentStatus.SUCCESS
        assert resp2.data["attempt_number"] == 2

        pending_booking.refresh_from_db()
        assert pending_booking.status == BookingStatus.CONFIRMED
        assert Payment.objects.filter(booking=pending_booking).count() == 2

    def test_payment_against_cancelled_booking_rejected_409(
        self, api_client, auth_headers_patient, pending_booking
    ):
        pending_booking.status = BookingStatus.CANCELLED
        pending_booking.save()

        url = reverse("payment-create")
        headers = {**auth_headers_patient, "HTTP_IDEMPOTENCY_KEY": f"key_{uuid.uuid4()}"}
        response = api_client.post(
            url, {"booking_id": str(pending_booking.id)}, format="json", **headers
        )

        assert response.status_code == status.HTTP_409_CONFLICT
        assert response.data["error"]["code"] == "BOOKING_CANCELLED"

    def test_missing_idempotency_key_rejected_400(
        self, api_client, auth_headers_patient, pending_booking
    ):
        url = reverse("payment-create")
        # No HTTP_IDEMPOTENCY_KEY header supplied
        response = api_client.post(
            url, {"booking_id": str(pending_booking.id)}, format="json", **auth_headers_patient
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Idempotency-Key" in response.data["error"]["message"]
