"""
Payment and Webhook Event Domain Models:
Tracks payment attempts, idempotency keys, provider references, and the webhook audit ledger.
"""

import uuid
from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models

from bookings.models import Booking


class PaymentStatus(models.TextChoices):
    INITIATED = "INITIATED", "Initiated"
    SUCCESS = "SUCCESS", "Success"
    FAILED = "FAILED", "Failed"


class Payment(models.Model):
    """Payment attempt for a specific booking."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    booking = models.ForeignKey(
        Booking,
        on_delete=models.PROTECT,
        related_name="payments",
        db_index=True,
    )
    idempotency_key = models.CharField(
        max_length=255,
        unique=True,
        db_index=True,
        help_text="Unique client-supplied idempotency key preventing duplicate payment attempts.",
    )
    provider_reference = models.CharField(
        max_length=255,
        unique=True,
        db_index=True,
        help_text="Unique transaction reference assigned by the payment gateway.",
    )
    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
        help_text="Payment amount.",
    )
    status = models.CharField(
        max_length=20,
        choices=PaymentStatus.choices,
        default=PaymentStatus.INITIATED,
        db_index=True,
    )
    attempt_number = models.PositiveIntegerField(
        default=1,
        help_text="Sequential attempt number for the associated booking.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "payments"
        verbose_name = "payment attempt"
        verbose_name_plural = "payment attempts"
        constraints = [
            models.UniqueConstraint(
                fields=["idempotency_key"],
                name="unique_payment_idempotency_key",
            ),
            models.UniqueConstraint(
                fields=["provider_reference"],
                name="unique_payment_provider_reference",
            ),
            models.UniqueConstraint(
                fields=["booking", "attempt_number"],
                name="unique_booking_attempt_number",
            ),
            models.CheckConstraint(
                condition=models.Q(amount__gt=0),
                name="positive_payment_amount",
            ),
        ]
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return (
            f"Payment {self.id} [{self.status}] - Ref: {self.provider_reference} (₹{self.amount})"
        )


class WebhookEvent(models.Model):
    """Immutable idempotency ledger for incoming payment provider webhook events."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event_id = models.CharField(
        max_length=255,
        unique=True,
        db_index=True,
        help_text="Unique event ID assigned by the payment gateway.",
    )
    provider_reference = models.CharField(
        max_length=255,
        db_index=True,
        help_text="Transaction reference to which this event relates.",
    )
    payload_hash = models.CharField(
        max_length=64,
        help_text="SHA-256 hash of the verified raw request body for audit trail.",
    )
    received_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "webhook_events"
        verbose_name = "webhook event"
        verbose_name_plural = "webhook events"
        constraints = [
            models.UniqueConstraint(
                fields=["event_id"],
                name="unique_webhook_event_id",
            ),
        ]
        ordering = ["-received_at"]

    def __str__(self) -> str:
        return f"WebhookEvent {self.event_id} (Ref: {self.provider_reference})"
