"""
Payment HTTP Views:
- POST /api/v1/payments/ : Initiate idempotent payment attempt (authenticated)
- POST /api/v1/payments/webhook/ : Webhook receiver with HMAC authentication (provider)
"""

from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from common.exceptions import ValidationError
from common.throttling import WebhookRateThrottle
from payments.serializers import (
    PaymentCreateRequestSerializer,
    PaymentResponseSerializer,
    WebhookPayloadSerializer,
)
from payments.services import execute_payment_attempt, process_webhook_event


class PaymentCreateView(APIView):
    """Initiate an idempotent simulated payment attempt for a booking."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Initiate Payment Attempt",
        description=(
            "Processes a simulated payment against an existing booking. "
            "Requires an Idempotency-Key header to prevent duplicate charges upon retries."
        ),
        parameters=[
            OpenApiParameter(
                name="Idempotency-Key",
                type=str,
                location=OpenApiParameter.HEADER,
                description="Unique client idempotency token (e.g. UUIDv4).",
                required=False,
            ),
        ],
        request=PaymentCreateRequestSerializer,
        responses={
            201: PaymentResponseSerializer,
            200: PaymentResponseSerializer,
        },
    )
    def post(self, request):
        serializer = PaymentCreateRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Extract Idempotency Key from request headers (standard or custom) or payload fallback
        idempotency_key = (
            request.headers.get("Idempotency-Key")
            or request.headers.get("X-Idempotency-Key")
            or request.META.get("HTTP_IDEMPOTENCY_KEY")
            or request.META.get("HTTP_X_IDEMPOTENCY_KEY")
            or serializer.validated_data.get("idempotency_key")
        )

        if not idempotency_key:
            raise ValidationError(
                "Idempotency-Key must be provided via the 'Idempotency-Key' HTTP header."
            )

        payment, created = execute_payment_attempt(
            user=request.user,
            booking_id=serializer.validated_data["booking_id"],
            idempotency_key=str(idempotency_key),
            simulate_failure=serializer.validated_data.get("simulate_failure", False),
        )

        response_status = status.HTTP_201_CREATED if created else status.HTTP_200_OK
        return Response(PaymentResponseSerializer(payment).data, status=response_status)


class PaymentWebhookView(APIView):
    """Signed, idempotent webhook receiver for simulated payment gateway status updates."""

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [WebhookRateThrottle]

    @extend_schema(
        summary="Payment Provider Webhook Callback",
        description=(
            "Authenticates HMAC-SHA256 signature over raw payload and timestamp freshness. "
            "Guarantees duplicate delivery is harmless."
        ),
        parameters=[
            OpenApiParameter(
                name="X-Webhook-Timestamp",
                type=str,
                location=OpenApiParameter.HEADER,
                description="Unix epoch timestamp generated at provider dispatch.",
                required=True,
            ),
            OpenApiParameter(
                name="X-Webhook-Signature",
                type=str,
                location=OpenApiParameter.HEADER,
                description="Hex-encoded HMAC-SHA256 signature.",
                required=True,
            ),
        ],
        request=WebhookPayloadSerializer,
        responses={200: dict},
    )
    def post(self, request):
        raw_body = request.body
        timestamp = request.headers.get("X-Webhook-Timestamp") or request.META.get(
            "HTTP_X_WEBHOOK_TIMESTAMP"
        )
        signature = request.headers.get("X-Webhook-Signature") or request.META.get(
            "HTTP_X_WEBHOOK_SIGNATURE"
        )

        result = process_webhook_event(
            raw_body=raw_body,
            timestamp_header=timestamp,
            signature_header=signature,
        )
        return Response(result, status=status.HTTP_200_OK)
