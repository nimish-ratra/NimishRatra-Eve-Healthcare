"""
Payment Gateway Provider Abstraction and Deterministic Fake Provider.

The application domain logic depends only on the BasePaymentProvider interface,
never on concrete external third-party SDKs.
"""

import hashlib
import hmac
import json
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class PaymentResult:
    """Outcome returned by a payment provider charge attempt."""

    success: bool
    provider_reference: str
    error_message: str | None = None


class BasePaymentProvider(ABC):
    """Abstract interface defining required provider capabilities."""

    @abstractmethod
    def process_payment(
        self,
        amount: Decimal,
        booking_id: str,
        simulate_failure: bool = False,
    ) -> PaymentResult:
        """Executes a payment charge against the gateway."""
        pass


class FakePaymentProvider(BasePaymentProvider):
    """Deterministic simulated payment provider for local development, reviewer demos, and testing.

    - Completely zero network dependency.
    - Yields deterministic SUCCESS or FAILED based on simulation parameters.
    - Generates unique, stable provider references (e.g. 'pay_sim_<uuid>').
    - Provides a cryptographic signing utility for generating valid webhook test payloads.
    """

    def process_payment(
        self,
        amount: Decimal,
        booking_id: str,
        simulate_failure: bool = False,
    ) -> PaymentResult:
        provider_reference = f"pay_sim_{uuid.uuid4().hex[:16]}"

        if simulate_failure:
            return PaymentResult(
                success=False,
                provider_reference=provider_reference,
                error_message="Card declined by simulated issuing bank.",
            )

        return PaymentResult(
            success=True,
            provider_reference=provider_reference,
            error_message=None,
        )

    @staticmethod
    def create_signed_webhook_payload(
        event_id: str,
        provider_reference: str,
        event_type: str,  # 'payment.success' or 'payment.failed'
        amount: Decimal,
        secret: str,
        timestamp: int | None = None,
    ) -> tuple[bytes, dict[str, str]]:
        """Utility for tests and demo scripts to generate valid signed webhook payloads.
        Returns: (raw_body_bytes, headers_dict)
        """
        if timestamp is None:
            timestamp = int(time.time())

        payload_dict = {
            "event_id": event_id,
            "event_type": event_type,
            "provider_reference": provider_reference,
            "amount": str(amount),
            "timestamp": timestamp,
        }
        raw_body = json.dumps(payload_dict, separators=(",", ":")).encode("utf-8")

        # Compute HMAC-SHA256 signature over: timestamp + "." + raw_body
        signature_base = f"{timestamp}.".encode() + raw_body
        computed_signature = hmac.new(
            secret.encode("utf-8"),
            signature_base,
            hashlib.sha256,
        ).hexdigest()

        headers = {
            "Content-Type": "application/json",
            "X-Webhook-Timestamp": str(timestamp),
            "X-Webhook-Signature": computed_signature,
            "HTTP_X_WEBHOOK_TIMESTAMP": str(timestamp),
            "HTTP_X_WEBHOOK_SIGNATURE": computed_signature,
        }
        return raw_body, headers
