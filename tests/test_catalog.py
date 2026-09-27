"""
Catalog & Pricing Integration Tests:
Tests centre browsing, location filtering, admin catalogue operations, and offering pricing.
"""

from decimal import Decimal

import pytest
from django.urls import reverse
from rest_framework import status

from catalog.models import CentreTest, DiagnosticCentre, DiagnosticTest


@pytest.mark.django_db
class TestCatalog:
    def test_list_centres_public(self, api_client, centre):
        url = reverse("centre-list-create")
        response = api_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] >= 1
        names = [item["name"] for item in response.data["results"]]
        assert centre.name in names

    def test_list_centres_location_filter(self, api_client, centre):
        DiagnosticCentre.objects.create(name="Mumbai Diagnostics", location="Bandra, Mumbai")

        url = reverse("centre-list-create")
        response = api_client.get(url, {"location": "Gurugram"})

        assert response.status_code == status.HTTP_200_OK
        results = response.data["results"]
        assert len(results) == 1
        assert results[0]["name"] == centre.name

    def test_admin_create_centre_success(self, api_client, auth_headers_admin):
        url = reverse("centre-list-create")
        payload = {"name": "New Delhi Labs", "location": "Connaught Place, New Delhi"}
        response = api_client.post(url, payload, format="json", **auth_headers_admin)

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["name"] == "New Delhi Labs"
        assert DiagnosticCentre.objects.filter(name="New Delhi Labs").exists()

    def test_non_admin_create_centre_forbidden(self, api_client, auth_headers_patient):
        url = reverse("centre-list-create")
        payload = {"name": "Hacker Labs", "location": "Unknown"}
        response = api_client.post(url, payload, format="json", **auth_headers_patient)

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert response.data["error"]["code"] == "FORBIDDEN"

    def test_admin_register_diagnostic_test(self, api_client, auth_headers_admin):
        url = reverse("test-create")
        payload = {
            "code": "XRAY_CHEST",
            "name": "Chest X-Ray PA View",
            "description": "Digital radiographic scan of chest",
        }
        response = api_client.post(url, payload, format="json", **auth_headers_admin)

        assert response.status_code == status.HTTP_201_CREATED
        assert DiagnosticTest.objects.filter(code="XRAY_CHEST").exists()

    def test_admin_add_centre_offering_with_price(
        self, api_client, auth_headers_admin, centre, diagnostic_test
    ):
        url = reverse("centre-offerings", kwargs={"id": centre.id})
        payload = {"test_id": str(diagnostic_test.id), "price": "1850.50"}
        response = api_client.post(url, payload, format="json", **auth_headers_admin)

        assert response.status_code == status.HTTP_201_CREATED
        assert Decimal(response.data["price"]) == Decimal("1850.50")
        assert CentreTest.objects.filter(centre=centre, test=diagnostic_test).exists()

    def test_duplicate_centre_offering_rejected(
        self, api_client, auth_headers_admin, centre_test_offering
    ):
        url = reverse("centre-offerings", kwargs={"id": centre_test_offering.centre_id})
        payload = {
            "test_id": str(centre_test_offering.test_id),
            "price": "3000.00",
        }
        response = api_client.post(url, payload, format="json", **auth_headers_admin)

        assert response.status_code == status.HTTP_409_CONFLICT
        assert response.data["error"]["code"] == "CONFLICT"

    def test_list_centre_offerings_public(self, api_client, centre_test_offering):
        url = reverse("centre-offerings", kwargs={"id": centre_test_offering.centre_id})
        response = api_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        results = response.data["results"]
        assert len(results) == 1
        assert results[0]["test_code"] == centre_test_offering.test.code
        assert Decimal(results[0]["price"]) == centre_test_offering.price

    def test_inactive_centre_offerings_hidden(self, api_client, centre_test_offering):
        centre_test_offering.is_active = False
        centre_test_offering.save()

        url = reverse("centre-offerings", kwargs={"id": centre_test_offering.centre_id})
        response = api_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] == 0
