"""
Operational Health Check Endpoints:
- GET /health/live/ : Process liveness (does not fail if DB is temporarily unreachable).
- GET /health/ready/ : Dependency readiness (validates DB connectivity).
"""

import logging

from django.db import connection
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

logger = logging.getLogger("eve_healthcare.health")


class HealthLiveView(APIView):
    """Answers: Is the application process running and alive?"""

    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(
        summary="Process Liveness Check",
        description="Returns 200 OK if the application process is running. Does not check dependencies.",
        responses={
            200: inline_serializer(
                name="HealthLiveResponse",
                fields={"status": serializers.CharField(default="alive")},
            )
        },
    )
    def get(self, request):
        return Response({"status": "alive"}, status=status.HTTP_200_OK)


class HealthReadyView(APIView):
    """Answers: Can the application safely serve traffic? Validates database connectivity."""

    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(
        summary="Dependency Readiness Check",
        description="Returns 200 OK if the database and essential dependencies are reachable, or 503 if unavailable.",
        responses={
            200: inline_serializer(
                name="HealthReadyResponse",
                fields={
                    "status": serializers.CharField(default="ready"),
                    "database": serializers.CharField(default="connected"),
                },
            ),
            503: inline_serializer(
                name="HealthReadyUnavailableResponse",
                fields={
                    "status": serializers.CharField(default="unavailable"),
                    "database": serializers.CharField(default="disconnected"),
                    "error": serializers.CharField(),
                },
            ),
        },
    )
    def get(self, request):
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1;")
                cursor.fetchone()
            return Response(
                {"status": "ready", "database": "connected"},
                status=status.HTTP_200_OK,
            )
        except Exception as exc:
            logger.error(f"Readiness check failed: {exc}")
            return Response(
                {
                    "status": "unavailable",
                    "database": "disconnected",
                    "error": str(exc),
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
