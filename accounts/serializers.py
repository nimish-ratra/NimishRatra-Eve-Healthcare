"""
Authentication Serializers:
Defines request and response shapes for user registration and JWT authentication.
"""

from rest_framework import serializers

from accounts.models import User


class SignupRequestSerializer(serializers.Serializer):
    """Input payload for patient account creation."""

    email = serializers.EmailField(
        required=True,
        help_text="User's unique email address.",
    )
    password = serializers.CharField(
        required=True,
        write_only=True,
        min_length=8,
        style={"input_type": "password"},
        help_text="Password must contain at least 8 characters.",
    )

    def validate_email(self, value: str) -> str:
        normalized = value.strip().lower()
        if User.objects.filter(email=normalized).exists():
            raise serializers.ValidationError("A user with this email address already exists.")
        return normalized


class UserResponseSerializer(serializers.ModelSerializer):
    """Safe public representation of user identity."""

    class Meta:
        model = User
        fields = ("id", "email", "is_admin", "created_at")
        read_only_fields = fields


class LoginRequestSerializer(serializers.Serializer):
    """Input payload for credentials authentication."""

    email = serializers.EmailField(required=True)
    password = serializers.CharField(
        required=True,
        write_only=True,
        style={"input_type": "password"},
    )

    def validate_email(self, value: str) -> str:
        return value.strip().lower()


class TokenResponseSerializer(serializers.Serializer):
    """Response containing access/refresh JWT tokens and authenticated user summary."""

    access = serializers.CharField(help_text="Short-lived Bearer access token (15 mins).")
    refresh = serializers.CharField(help_text="Longer-lived refresh token (7 days).")
    user = UserResponseSerializer()
