"""
Operational Health Endpoints & Documentation Tests:
Tests process liveness, database readiness, OpenAPI schema generation, and correlation IDs.
"""

from unittest.mock import patch

import pytest
from django.urls import reverse
from rest_framework import status


@pytest.mark.django_db
class TestOperations:
    def test_health_live_endpoint(self, api_client):
        url = reverse("health-live")
        response = api_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["status"] == "alive"

    def test_health_ready_endpoint_connected(self, api_client):
        url = reverse("health-ready")
        response = api_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["status"] == "ready"
        assert response.data["database"] == "connected"

    def test_health_ready_endpoint_disconnected(self, api_client):
        url = reverse("health-ready")
        with patch(
            "django.db.connection.cursor", side_effect=Exception("Database connection timeout")
        ):
            response = api_client.get(url)

        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        assert response.data["status"] == "unavailable"
        assert response.data["database"] == "disconnected"

    def test_openapi_schema_endpoint(self, api_client):
        url = reverse("schema")
        response = api_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert "openapi" in response.content.decode("utf-8").lower()

    def test_swagger_ui_accessible(self, api_client):
        url = reverse("swagger-ui")
        response = api_client.get(url)

        assert response.status_code == status.HTTP_200_OK

    def test_redoc_ui_accessible(self, api_client):
        url = reverse("redoc")
        response = api_client.get(url)

        assert response.status_code == status.HTTP_200_OK

    def test_request_id_header_injected_and_propagated(self, api_client):
        url = reverse("health-live")
        custom_req_id = "test-custom-correlation-id-12345"

        # Propagate custom ID
        response = api_client.get(url, HTTP_X_REQUEST_ID=custom_req_id)
        assert response.status_code == status.HTTP_200_OK
        assert response.headers.get("X-Request-ID") == custom_req_id

        # Generate fresh ID when none supplied
        auto_response = api_client.get(url)
        assert auto_response.status_code == status.HTTP_200_OK
        assert "X-Request-ID" in auto_response.headers
        assert len(auto_response.headers["X-Request-ID"]) > 0
