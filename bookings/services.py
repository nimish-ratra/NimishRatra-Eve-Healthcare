"""
Booking Domain Services & Centralized State Machine:
Encapsulates booking creation with authoritative price snapshotting,
transactional cancellation, and strict state transitions.
"""

import datetime
import logging
import uuid

from django.db import transaction

from bookings.models import Booking, BookingStatus
from catalog.selectors import get_active_centre_test
from common.exceptions import (
    BookingCancelledError,
    BookingNotFoundError,
    IllegalStateTransitionError,
)

logger = logging.getLogger("eve_healthcare.bookings")

# Authoritative State Machine Transition Table
# Mapping: current_status -> set of allowable next_statuses
LEGAL_TRANSITIONS: dict[str, set[str]] = {
    BookingStatus.PENDING: {
        BookingStatus.CONFIRMED,
        BookingStatus.FAILED,
        BookingStatus.CANCELLED,
    },
    BookingStatus.FAILED: {
        # Retry path: a new successful payment attempt can transition a FAILED booking to CONFIRMED
        BookingStatus.CONFIRMED,
        # Retry failure: another payment attempt fails
        BookingStatus.FAILED,
        # Cancellation permitted after failed payment attempts
        BookingStatus.CANCELLED,
    },
    BookingStatus.CONFIRMED: {
        # Cancellation permitted under policy
        BookingStatus.CANCELLED,
    },
    BookingStatus.CANCELLED: set(),  # Terminal state: NEVER resurrected under any circumstance
}


class BookingStateMachine:
    """Centralized, deterministic state machine controlling all Booking lifecycle mutations."""

    @staticmethod
    def apply_transition(booking: Booking, new_status: str) -> Booking:
        """Validates and applies a state transition to a locked booking.
        Increments the version counter for optimistic concurrency tracking.
        """
        current_status = booking.status
        allowed = LEGAL_TRANSITIONS.get(current_status, set())

        if new_status not in allowed:
            logger.warning(
                f"Illegal state transition attempted on Booking {booking.id}: "
                f"'{current_status}' -> '{new_status}'"
            )
            if current_status == BookingStatus.CANCELLED:
                raise BookingCancelledError("Cancelled booking cannot be modified or resurrected.")
            raise IllegalStateTransitionError(
                f"Cannot transition booking from '{current_status}' to '{new_status}'."
            )

        booking.status = new_status
        booking.version += 1
        booking.save(update_fields=["status", "version", "updated_at"])
        logger.info(
            f"Booking {booking.id} transitioned: {current_status} -> {new_status} (v{booking.version})"
        )
        return booking


def create_booking(user, centre_test_id: uuid.UUID, appointment_at: datetime.datetime) -> Booking:
    """Creates a new patient booking with server-authoritative price snapshotting.

    Rule: Client NEVER supplies the final amount.
    1. Look up the active CentreTest offering.
    2. Extract offering.price.
    3. Persist into Booking.amount as an immutable snapshot.
    """
    centre_test = get_active_centre_test(centre_test_id=centre_test_id)
    authoritative_amount = centre_test.price

    with transaction.atomic():
        booking = Booking.objects.create(
            user=user,
            centre_test=centre_test,
            appointment_at=appointment_at,
            amount=authoritative_amount,
            status=BookingStatus.PENDING,
            version=1,
        )

    logger.info(
        f"Created booking {booking.id} for user {user.id} with authoritative amount ₹{booking.amount}"
    )
    return booking


def cancel_booking(booking_id: uuid.UUID, user) -> Booking:
    """Cancels a booking owned by the caller.

    Concurrency Guarantees:
    - Starts a database transaction.
    - Acquires PostgreSQL row lock (select_for_update) on the Booking row first.
    - Re-reads committed state to ensure the booking wasn't already confirmed or cancelled.
    - Applies CANCELLED transition via the centralized BookingStateMachine.
    """
    with transaction.atomic():
        try:
            # Canonical lock order: Lock Booking first
            booking = (
                Booking.objects.select_for_update()
                .select_related("centre_test__centre", "centre_test__test")
                .get(id=booking_id, user=user)
            )
        except (Booking.DoesNotExist, ValueError) as err:
            raise BookingNotFoundError(
                "Booking does not exist or is not accessible to this user."
            ) from err

        if booking.status == BookingStatus.CANCELLED:
            raise BookingCancelledError("This booking is already cancelled.")

        # Centralized state machine transition
        booking = BookingStateMachine.apply_transition(booking, BookingStatus.CANCELLED)

    return booking
