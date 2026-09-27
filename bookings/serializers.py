"""
Booking Serializers:
Defines request and response shapes for creating, retrieving, and cancelling appointments.
"""

from django.utils import timezone
from rest_framework import serializers

from bookings.models import Booking


class BookingCreateRequestSerializer(serializers.Serializer):
    """Payload to initiate a new diagnostic appointment booking."""

    centre_test_id = serializers.UUIDField(
        required=True,
        help_text="UUID of the specific diagnostic test offering at a chosen centre.",
    )
    appointment_at = serializers.DateTimeField(
        required=True,
        help_text="Timezone-aware datetime scheduled in the future (ISO-8601).",
    )

    def validate_appointment_at(self, value):
        if not timezone.is_aware(value):
            raise serializers.ValidationError("Appointment time must be timezone-aware.")
        if value <= timezone.now():
            raise serializers.ValidationError("Appointment time must be scheduled in the future.")
        return value


class BookingResponseSerializer(serializers.ModelSerializer):
    """Detailed booking representation returned to the authenticated patient."""

    user_id = serializers.UUIDField(source="user.id", read_only=True)
    centre_test_id = serializers.UUIDField(source="centre_test.id", read_only=True)
    centre_name = serializers.CharField(source="centre_test.centre.name", read_only=True)
    centre_location = serializers.CharField(source="centre_test.centre.location", read_only=True)
    test_code = serializers.CharField(source="centre_test.test.code", read_only=True)
    test_name = serializers.CharField(source="centre_test.test.name", read_only=True)

    class Meta:
        model = Booking
        fields = (
            "id",
            "user_id",
            "centre_test_id",
            "centre_name",
            "centre_location",
            "test_code",
            "test_name",
            "appointment_at",
            "amount",
            "status",
            "version",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields
