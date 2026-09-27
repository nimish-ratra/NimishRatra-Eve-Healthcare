"""
Pytest Fixtures and Test Helpers for EVE Healthcare API.
"""

from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.models import User
from bookings.models import Booking, BookingStatus
from catalog.models import CentreTest, DiagnosticCentre, DiagnosticTest
from payments.providers import FakePaymentProvider


@pytest.fixture
def api_client():
    """Unauthenticated DRF APIClient."""
    return APIClient()


@pytest.fixture
def patient_user(db):
    """Standard authenticated patient user."""
    return User.objects.create_user(
        email="patient@example.com",
        password="ValidPassword123!",
        is_admin=False,
    )


@pytest.fixture
def other_patient_user(db):
    """A second patient user for cross-tenant / ownership isolation testing."""
    return User.objects.create_user(
        email="other.patient@example.com",
        password="ValidPassword123!",
        is_admin=False,
    )


@pytest.fixture
def admin_user(db):
    """Administrator user with catalogue mutation privileges."""
    return User.objects.create_user(
        email="admin@example.com",
        password="AdminPassword123!",
        is_admin=True,
        is_staff=True,
    )


@pytest.fixture
def auth_headers_patient(patient_user):
    """Authorization headers for patient_user."""
    refresh = RefreshToken.for_user(patient_user)
    return {"HTTP_AUTHORIZATION": f"Bearer {refresh.access_token}"}


@pytest.fixture
def auth_headers_other_patient(other_patient_user):
    """Authorization headers for other_patient_user."""
    refresh = RefreshToken.for_user(other_patient_user)
    return {"HTTP_AUTHORIZATION": f"Bearer {refresh.access_token}"}


@pytest.fixture
def auth_headers_admin(admin_user):
    """Authorization headers for admin_user."""
    refresh = RefreshToken.for_user(admin_user)
    return {"HTTP_AUTHORIZATION": f"Bearer {refresh.access_token}"}


@pytest.fixture
def centre(db):
    """Sample diagnostic laboratory centre."""
    return DiagnosticCentre.objects.create(
        name="Gurugram Diagnostic Centre",
        location="Sector 44, Gurugram",
        is_active=True,
    )


@pytest.fixture
def diagnostic_test(db):
    """Sample canonical diagnostic test."""
    return DiagnosticTest.objects.create(
        code="MRI_BRAIN",
        name="MRI Brain with Contrast",
        description="High resolution brain MRI scan",
        is_active=True,
    )


@pytest.fixture
def centre_test_offering(centre, diagnostic_test):
    """Centre-specific offering with an authoritative price of ₹2500.00."""
    return CentreTest.objects.create(
        centre=centre,
        test=diagnostic_test,
        price=Decimal("2500.00"),
        is_active=True,
    )


@pytest.fixture
def pending_booking(patient_user, centre_test_offering):
    """Booking in PENDING status owned by patient_user."""
    appointment_time = timezone.now() + timezone.timedelta(days=2)
    return Booking.objects.create(
        user=patient_user,
        centre_test=centre_test_offering,
        appointment_at=appointment_time,
        amount=centre_test_offering.price,
        status=BookingStatus.PENDING,
        version=1,
    )


@pytest.fixture
def webhook_signer():
    """Helper function to create cryptographically signed webhook requests."""

    def _signer(event_id, provider_reference, event_type, amount, secret, timestamp=None):
        return FakePaymentProvider.create_signed_webhook_payload(
            event_id=event_id,
            provider_reference=provider_reference,
            event_type=event_type,
            amount=amount,
            secret=secret,
            timestamp=timestamp,
        )

    return _signer
