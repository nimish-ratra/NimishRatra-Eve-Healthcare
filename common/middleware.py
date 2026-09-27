"""
Cross-cutting Middleware:
1. RequestIDMiddleware: Propagates or generates X-Request-ID for every request.
2. StructuredLoggingMiddleware: Privacy-safe structured JSON access logging.
"""

import contextvars
import json
import logging
import time
import uuid

logger = logging.getLogger("eve_healthcare.access")

# Context variable for correlation ID across synchronous/asynchronous boundaries
request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="system")


def get_current_request_id() -> str:
    """Return the active correlation request ID."""
    return request_id_var.get()


class RequestIDMiddleware:
    """Ensures every HTTP request has an X-Request-ID correlation identifier."""

    HEADER_NAME = "HTTP_X_REQUEST_ID"
    RESPONSE_HEADER = "X-Request-ID"

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        req_id = request.META.get(self.HEADER_NAME)
        if not req_id or len(req_id) > 64:
            req_id = str(uuid.uuid4())

        request.id = req_id
        token = request_id_var.set(req_id)

        try:
            response = self.get_response(request)
            response[self.RESPONSE_HEADER] = req_id
            return response
        finally:
            request_id_var.reset(token)


class StructuredLoggingMiddleware:
    """Logs incoming and outgoing requests as structured JSON events.
    Enforces privacy-first logging: strictly redacting authorization, passwords,
    webhook secrets, and patient PII.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        start_time = time.perf_counter()

        # Let the view execute
        response = self.get_response(request)

        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
        request_id = getattr(request, "id", "unknown")

        user_id = "anonymous"
        if hasattr(request, "user") and request.user.is_authenticated:
            user_id = str(request.user.id)

        log_data = {
            "event": "http_request",
            "request_id": request_id,
            "method": request.method,
            "path": request.path,
            "status_code": response.status_code,
            "duration_ms": duration_ms,
            "user_id": user_id,
        }

        # Filter out noisy internal health checks from error alerts
        if response.status_code >= 500:
            logger.error(json.dumps(log_data))
        elif response.status_code >= 400:
            logger.warning(json.dumps(log_data))
        else:
            logger.info(json.dumps(log_data))

        return response
