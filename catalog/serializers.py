"""
Catalog Serializers:
Defines request and response shapes for diagnostic centres, tests, and offerings.
"""

from decimal import Decimal

from rest_framework import serializers

from catalog.models import CentreTest, DiagnosticCentre, DiagnosticTest


class DiagnosticCentreSerializer(serializers.ModelSerializer):
    """Public representation of a diagnostic centre."""

    class Meta:
        model = DiagnosticCentre
        fields = ("id", "name", "location", "is_active", "created_at")
        read_only_fields = fields


class DiagnosticCentreCreateSerializer(serializers.Serializer):
    """Admin payload to create a new diagnostic centre."""

    name = serializers.CharField(max_length=255, required=True)
    location = serializers.CharField(max_length=255, required=True)

    def validate_name(self, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise serializers.ValidationError("Centre name cannot be empty.")
        return cleaned

    def validate_location(self, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise serializers.ValidationError("Location cannot be empty.")
        return cleaned


class DiagnosticTestSerializer(serializers.ModelSerializer):
    """Public representation of a diagnostic test."""

    class Meta:
        model = DiagnosticTest
        fields = ("id", "code", "name", "description", "is_active")
        read_only_fields = fields


class DiagnosticTestCreateSerializer(serializers.Serializer):
    """Admin payload to create a reusable diagnostic test."""

    code = serializers.CharField(max_length=50, required=True)
    name = serializers.CharField(max_length=255, required=True)
    description = serializers.CharField(required=False, allow_blank=True, default="")

    def validate_code(self, value: str) -> str:
        cleaned = value.strip().upper()
        if DiagnosticTest.objects.filter(code=cleaned).exists():
            raise serializers.ValidationError("A diagnostic test with this code already exists.")
        return cleaned


class CentreTestSummarySerializer(serializers.ModelSerializer):
    """Test offering details for centre-specific listing."""

    centre_test_id = serializers.UUIDField(source="id", read_only=True)
    test_id = serializers.UUIDField(source="test.id", read_only=True)
    test_code = serializers.CharField(source="test.code", read_only=True)
    test_name = serializers.CharField(source="test.name", read_only=True)
    test_description = serializers.CharField(source="test.description", read_only=True)
    price = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        model = CentreTest
        fields = (
            "centre_test_id",
            "test_id",
            "test_code",
            "test_name",
            "test_description",
            "price",
        )
        read_only_fields = fields


class CentreTestCreateSerializer(serializers.Serializer):
    """Admin payload to map a diagnostic test to a centre with authoritative pricing."""

    test_id = serializers.UUIDField(required=True)
    price = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        min_value=Decimal("0.01"),
        required=True,
    )
