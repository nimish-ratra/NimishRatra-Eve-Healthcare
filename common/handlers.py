"""
Global Exception Handler for Django REST Framework.

Converts all domain exceptions, DRF validation errors, authentication failures,
and uncaught 500 server errors into a unified, predictable JSON envelope:

{
    "error": {
        "code": "ERROR_CODE",
        "message": "Human readable description",
        "details": { ... },
        "request_id": "uuid"
    }
}
"""

import logging
from typing import Any

from django.core.exceptions import PermissionDenied
from django.http import Http404
from rest_framework import exceptions as drf_exceptions
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_default_exception_handler

from common.exceptions import BaseAppException, WebhookEventDuplicateError
from common.middleware import get_current_request_id

logger = logging.getLogger("eve_healthcare.exceptions")


def custom_exception_handler(exc: Exception, context: dict[str, Any]) -> Response | None:
    """Standardized exception handler for all API views."""
    request_id = get_current_request_id()

    # 1. Custom Domain Exceptions
    if isinstance(exc, WebhookEventDuplicateError):
        # Specific requirement: Duplicate webhook delivery is acknowledged with HTTP 200 without side effects
        return Response(
            {
                "status": "acknowledged",
                "code": exc.code,
                "message": exc.message,
                "request_id": request_id,
            },
            status=200,
        )

    if isinstance(exc, BaseAppException):
        response_data = {
            "error": {
                "code": exc.code,
                "message": exc.message,
                "details": exc.details or {},
                "request_id": request_id,
            }
        }
        return Response(response_data, status=exc.status_code)

    # 2. Django Core Standard Exceptions
    if isinstance(exc, Http404):
        return Response(
            {
                "error": {
                    "code": "RESOURCE_NOT_FOUND",
                    "message": str(exc) or "The requested resource was not found.",
                    "details": {},
                    "request_id": request_id,
                }
            },
            status=404,
        )

    if isinstance(exc, PermissionDenied):
        return Response(
            {
                "error": {
                    "code": "FORBIDDEN",
                    "message": "You do not have permission to perform this action.",
                    "details": {},
                    "request_id": request_id,
                }
            },
            status=403,
        )

    # 3. DRF Built-in Exceptions (Validation, Auth, Not Found, Method Not Allowed, Throttled)
    drf_response = drf_default_exception_handler(exc, context)
    if drf_response is not None:
        code = "API_ERROR"
        message = "An error occurred while processing the request."
        details = drf_response.data

        if isinstance(exc, drf_exceptions.ValidationError):
            code = "VALIDATION_ERROR"
            message = "The request payload failed field or schema validation."
        elif isinstance(
            exc, (drf_exceptions.NotAuthenticated, drf_exceptions.AuthenticationFailed)
        ):
            code = "AUTHENTICATION_FAILED"
            message = "Authentication credentials were not provided or are invalid."
        elif isinstance(exc, drf_exceptions.PermissionDenied):
            code = "FORBIDDEN"
            message = "You do not have permission to perform this action."
        elif isinstance(exc, drf_exceptions.NotFound):
            code = "RESOURCE_NOT_FOUND"
            message = "Resource not found."
        elif isinstance(exc, drf_exceptions.Throttled):
            code = "RATE_LIMIT_EXCEEDED"
            message = f"Request was throttled. Expected available in {exc.wait} seconds."
        elif isinstance(exc, drf_exceptions.MethodNotAllowed):
            code = "METHOD_NOT_ALLOWED"
            message = f"Method {context.get('request').method} is not allowed for this endpoint."

        # Simplify single detail strings
        if isinstance(details, dict) and "detail" in details and len(details) == 1:
            message = str(details["detail"])
            details = {}
        elif isinstance(details, list) and len(details) == 1:
            message = str(details[0])
            details = {}

        return Response(
            {
                "error": {
                    "code": code,
                    "message": message,
                    "details": details,
                    "request_id": request_id,
                }
            },
            status=drf_response.status_code,
        )

    # 4. Unhandled 500 Internal Errors
    logger.exception(
        f"Unhandled server error [request_id={request_id}]: {exc}",
        extra={"request_id": request_id},
    )
    return Response(
        {
            "error": {
                "code": "INTERNAL_SERVER_ERROR",
                "message": "An internal server error occurred. Please contact support with the request ID.",
                "details": {},
                "request_id": request_id,
            }
        },
        status=500,
    )
