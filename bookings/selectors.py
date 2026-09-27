"""
Booking Selectors:
Read-only queries enforcing strict patient ownership boundaries and anti-enumeration.
"""

import uuid

from django.db.models import QuerySet

from bookings.models import Booking
from common.exceptions import BookingNotFoundError


def list_user_bookings(user) -> QuerySet[Booking]:
    """Returns all bookings created by the authenticated patient."""
    return (
        Booking.objects.filter(user=user)
        .select_related("centre_test__centre", "centre_test__test", "user")
        .order_by("-created_at")
    )


def get_user_booking_by_id(booking_id: uuid.UUID, user) -> Booking:
    """Retrieves a booking strictly owned by the caller.
    Anti-enumeration protection: querying by both booking ID and user ensures that
    another patient's booking is indistinguishable from a non-existent ID (HTTP 404).
    """
    try:
        return Booking.objects.select_related(
            "centre_test__centre",
            "centre_test__test",
            "user",
        ).get(id=booking_id, user=user)
    except (Booking.DoesNotExist, ValueError) as err:
        raise BookingNotFoundError(
            "Booking does not exist or is not accessible to this user."
        ) from err
