"""
Domain Exceptions and Stable Named Error Codes.

Every business rule violation raises an explicit DomainException.
The global exception handler transforms these into structured HTTP responses
with stable machine-readable error codes.
"""

from typing import Any


class BaseAppException(Exception):
    """Base exception for all application-level errors."""

    default_code: str = "INTERNAL_ERROR"
    default_message: str = "An unexpected error occurred."
    status_code: int = 500

    def __init__(
        self,
        message: str | None = None,
        code: str | None = None,
        status_code: int | None = None,
        details: Any = None,
    ):
        self.message = message or self.default_message
        self.code = code or self.default_code
        self.status_code = status_code or self.status_code
        self.details = details
        super().__init__(self.message)


class NotFoundError(BaseAppException):
    default_code = "RESOURCE_NOT_FOUND"
    default_message = "Requested resource was not found."
    status_code = 404


class BookingNotFoundError(NotFoundError):
    default_code = "BOOKING_NOT_FOUND"
    default_message = "Booking does not exist or is not accessible to this user."


class ConflictError(BaseAppException):
    default_code = "CONFLICT"
    default_message = "A business conflict occurred."
    status_code = 409


class BookingNotPendingError(ConflictError):
    default_code = "BOOKING_NOT_PENDING"
    default_message = "Operation requires the booking to be in PENDING status."


class BookingCancelledError(ConflictError):
    default_code = "BOOKING_CANCELLED"
    default_message = "The booking is cancelled and cannot be paid, resurrected, or modified."


class OfferingUnavailableError(ConflictError):
    default_code = "OFFERING_UNAVAILABLE"
    default_message = "The diagnostic centre test offering is inactive or unavailable."


class InvalidPaymentStateError(ConflictError):
    default_code = "INVALID_PAYMENT_STATE"
    default_message = "Payment action is inconsistent with the current payment/booking state."


class IdempotencyKeyReusedError(ConflictError):
    default_code = "IDEMPOTENCY_KEY_REUSED"
    default_message = "The idempotency key has already been used for a different booking or intent."


class IllegalStateTransitionError(ConflictError):
    default_code = "ILLEGAL_STATE_TRANSITION"
    default_message = "The requested state transition is not permitted by the state machine."


class PaymentAmountMismatchError(ConflictError):
    default_code = "AMOUNT_MISMATCH"
    default_message = "Supplied payment amount does not match the authoritative booking amount."


class ProviderReferenceNotFoundError(NotFoundError):
    default_code = "PROVIDER_REFERENCE_NOT_FOUND"
    default_message = "No payment attempt found matching the provider reference."
    status_code = 404


class AuthenticationError(BaseAppException):
    default_code = "AUTHENTICATION_FAILED"
    default_message = "Authentication credentials were not provided or are invalid."
    status_code = 401


class WebhookSignatureInvalidError(BaseAppException):
    default_code = "WEBHOOK_SIGNATURE_INVALID"
    default_message = "Webhook HMAC-SHA256 signature is missing, malformed, or invalid."
    status_code = 401


class WebhookTimestampStaleError(BaseAppException):
    default_code = "WEBHOOK_TIMESTAMP_STALE"
    default_message = "Webhook timestamp falls outside the acceptable freshness window."
    status_code = 401


class WebhookEventDuplicateError(BaseAppException):
    default_code = "WEBHOOK_EVENT_DUPLICATE"
    default_message = "Webhook event has already been received and processed."
    status_code = 200  # Duplicate delivery acknowledged without side effects


class AuthorizationPermissionError(BaseAppException):
    default_code = "FORBIDDEN"
    default_message = "You do not have permission to perform this action."
    status_code = 403


class ValidationError(BaseAppException):
    default_code = "VALIDATION_ERROR"
    default_message = "The request payload failed validation."
    status_code = 400
