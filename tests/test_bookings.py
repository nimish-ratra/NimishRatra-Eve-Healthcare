"""
Booking & State Machine Integration Tests:
Tests authoritative price snapshotting, ownership isolation, anti-enumeration,
past appointment validation, and cancellation rules.
"""

from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework import status

from bookings.models import BookingStatus


@pytest.mark.django_db
class TestBookings:
    def test_create_booking_authoritative_price_snapshot(
        self, api_client, auth_headers_patient, centre_test_offering
    ):
        url = reverse("booking-list-create")
        future_time = timezone.now() + timezone.timedelta(days=3)
        # Malicious client tries to send amount = 1.00
        payload = {
            "centre_test_id": str(centre_test_offering.id),
            "appointment_at": future_time.isoformat(),
            "amount": "1.00",
        }
        response = api_client.post(url, payload, format="json", **auth_headers_patient)

        assert response.status_code == status.HTTP_201_CREATED
        data = response.data
        # Price must NOT be 1.00; must be authoritative offering price 2500.00
        assert Decimal(data["amount"]) == Decimal("2500.00")
        assert data["status"] == BookingStatus.PENDING
        assert data["version"] == 1

    def test_booking_snapshot_immutable_after_offering_price_update(
        self, api_client, auth_headers_patient, centre_test_offering
    ):
        # 1. Create booking at original price ₹2500.00
        url = reverse("booking-list-create")
        future_time = timezone.now() + timezone.timedelta(days=3)
        response = api_client.post(
            url,
            {
                "centre_test_id": str(centre_test_offering.id),
                "appointment_at": future_time.isoformat(),
            },
            format="json",
            **auth_headers_patient,
        )
        booking_id = response.data["id"]

        # 2. Centre modifies offering price tomorrow to ₹3500.00
        centre_test_offering.price = Decimal("3500.00")
        centre_test_offering.save()

        # 3. Retrieve historical booking; amount must remain ₹2500.00!
        detail_url = reverse("booking-detail", kwargs={"id": booking_id})
        detail_resp = api_client.get(detail_url, **auth_headers_patient)
        assert Decimal(detail_resp.data["amount"]) == Decimal("2500.00")

    def test_create_booking_past_appointment_rejected(
        self, api_client, auth_headers_patient, centre_test_offering
    ):
        url = reverse("booking-list-create")
        past_time = timezone.now() - timezone.timedelta(hours=2)
        payload = {
            "centre_test_id": str(centre_test_offering.id),
            "appointment_at": past_time.isoformat(),
        }
        response = api_client.post(url, payload, format="json", **auth_headers_patient)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "appointment_at" in response.data["error"]["details"]

    def test_create_booking_inactive_offering_rejected(
        self, api_client, auth_headers_patient, centre_test_offering
    ):
        centre_test_offering.is_active = False
        centre_test_offering.save()

        url = reverse("booking-list-create")
        future_time = timezone.now() + timezone.timedelta(days=2)
        payload = {
            "centre_test_id": str(centre_test_offering.id),
            "appointment_at": future_time.isoformat(),
        }
        response = api_client.post(url, payload, format="json", **auth_headers_patient)

        assert response.status_code == status.HTTP_409_CONFLICT
        assert response.data["error"]["code"] == "OFFERING_UNAVAILABLE"

    def test_list_bookings_ownership_isolation(
        self, api_client, auth_headers_patient, auth_headers_other_patient, pending_booking
    ):
        # Patient A queries bookings: sees pending_booking
        url = reverse("booking-list-create")
        resp_a = api_client.get(url, **auth_headers_patient)
        assert resp_a.status_code == status.HTTP_200_OK
        assert resp_a.data["count"] == 1
        assert resp_a.data["results"][0]["id"] == str(pending_booking.id)

        # Patient B queries bookings: sees 0 bookings (isolated!)
        resp_b = api_client.get(url, **auth_headers_other_patient)
        assert resp_b.status_code == status.HTTP_200_OK
        assert resp_b.data["count"] == 0

    def test_get_booking_ownership_anti_enumeration(
        self, api_client, auth_headers_other_patient, pending_booking
    ):
        # Patient B attempts to retrieve Patient A's booking by ID
        url = reverse("booking-detail", kwargs={"id": pending_booking.id})
        response = api_client.get(url, **auth_headers_other_patient)

        # Must return 404 rather than 403 to prevent resource ID enumeration
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert response.data["error"]["code"] == "BOOKING_NOT_FOUND"

    def test_cancel_booking_success(self, api_client, auth_headers_patient, pending_booking):
        url = reverse("booking-cancel", kwargs={"id": pending_booking.id})
        response = api_client.post(url, **auth_headers_patient)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["status"] == BookingStatus.CANCELLED
        assert response.data["version"] == 2

        pending_booking.refresh_from_db()
        assert pending_booking.status == BookingStatus.CANCELLED
        assert pending_booking.version == 2

    def test_cancel_booking_unauthorized_anti_enumeration(
        self, api_client, auth_headers_other_patient, pending_booking
    ):
        url = reverse("booking-cancel", kwargs={"id": pending_booking.id})
        response = api_client.post(url, **auth_headers_other_patient)

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert response.data["error"]["code"] == "BOOKING_NOT_FOUND"

    def test_cancel_already_cancelled_booking_rejected(
        self, api_client, auth_headers_patient, pending_booking
    ):
        # Cancel first time
        url = reverse("booking-cancel", kwargs={"id": pending_booking.id})
        api_client.post(url, **auth_headers_patient)

        # Cancel second time
        response = api_client.post(url, **auth_headers_patient)
        assert response.status_code == status.HTTP_409_CONFLICT
        assert response.data["error"]["code"] == "BOOKING_CANCELLED"
