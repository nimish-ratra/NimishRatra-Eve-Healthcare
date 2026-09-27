"""
Booking Domain Model:
Maintains patient appointments, status transitions, versioning, and authoritative price snapshots.
"""

import uuid
from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models

from catalog.models import CentreTest


class BookingStatus(models.TextChoices):
    PENDING = "PENDING", "Pending Payment"
    CONFIRMED = "CONFIRMED", "Confirmed"
    FAILED = "FAILED", "Payment Failed"
    CANCELLED = "CANCELLED", "Cancelled"


class Booking(models.Model):
    """Patient diagnostic test booking."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="bookings",
        db_index=True,
    )
    centre_test = models.ForeignKey(
        CentreTest,
        on_delete=models.PROTECT,
        related_name="bookings",
    )
    appointment_at = models.DateTimeField(
        help_text="Timezone-aware appointment timestamp scheduled in the future.",
    )
    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
        help_text="Authoritative immutable price snapshot at the moment of booking.",
    )
    status = models.CharField(
        max_length=20,
        choices=BookingStatus.choices,
        default=BookingStatus.PENDING,
        db_index=True,
    )
    version = models.PositiveIntegerField(
        default=1,
        help_text="Optimistic concurrency tracking version incremented on each transition.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "bookings"
        verbose_name = "booking"
        verbose_name_plural = "bookings"
        indexes = [
            models.Index(fields=["user", "-created_at"], name="idx_bookings_user_created"),
            models.Index(fields=["appointment_at", "status"], name="idx_bookings_appt_status"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount__gt=0),
                name="positive_booking_amount",
            ),
        ]
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Booking {self.id} [{self.status}] - ₹{self.amount} for {self.user.email}"
