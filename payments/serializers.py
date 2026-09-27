"""
Payment Serializers:
Defines request and response schemas for initiating payments and receiving webhooks.
"""

from decimal import Decimal

from rest_framework import serializers

from payments.models import Payment


class PaymentCreateRequestSerializer(serializers.Serializer):
    """Payload to initiate a payment attempt."""

    booking_id = serializers.UUIDField(
        required=True,
        help_text="UUID of the diagnostic appointment booking to pay for.",
    )
    idempotency_key = serializers.CharField(
        required=False,
        max_length=255,
        help_text="Optional fallback if not supplied via the Idempotency-Key HTTP header.",
    )
    simulate_failure = serializers.BooleanField(
        required=False,
        default=False,
        help_text="Optional simulation control for testing failed card payments.",
    )


class PaymentResponseSerializer(serializers.ModelSerializer):
    """Detailed response representation of a payment attempt."""

    booking_id = serializers.UUIDField(source="booking.id", read_only=True)

    class Meta:
        model = Payment
        fields = (
            "id",
            "booking_id",
            "idempotency_key",
            "provider_reference",
            "amount",
            "status",
            "attempt_number",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class WebhookPayloadSerializer(serializers.Serializer):
    """Validated payload schema for incoming payment provider webhooks."""

    event_id = serializers.CharField(max_length=255, required=True)
    event_type = serializers.ChoiceField(
        choices=["payment.success", "payment.failed"],
        required=True,
    )
    provider_reference = serializers.CharField(max_length=255, required=True)
    amount = serializers.DecimalField(
        max_digits=10, decimal_places=2, min_value=Decimal("0.01"), required=True
    )
    timestamp = serializers.IntegerField(required=False)
