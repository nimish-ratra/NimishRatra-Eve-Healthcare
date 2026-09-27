"""
Authentication & Authorization Integration Tests:
Tests signup, login, refresh, anti-enumeration, and token authentication.
"""

import pytest
from django.urls import reverse
from rest_framework import status

from accounts.models import User


@pytest.mark.django_db
class TestAuthentication:
    def test_signup_success(self, api_client):
        url = reverse("auth-signup")
        payload = {"email": "new.patient@example.com", "password": "SecurePassword123!"}
        response = api_client.post(url, payload, format="json")

        assert response.status_code == status.HTTP_201_CREATED
        data = response.data
        assert data["email"] == "new.patient@example.com"
        assert "password" not in data
        assert "password_hash" not in data
        assert User.objects.filter(email="new.patient@example.com").exists()

    def test_signup_duplicate_email_rejected(self, api_client, patient_user):
        url = reverse("auth-signup")
        # Attempt to register using patient_user's email with different casing
        payload = {"email": "PATIENT@example.com", "password": "SecurePassword123!"}
        response = api_client.post(url, payload, format="json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "error" in response.data

    def test_signup_short_password_rejected(self, api_client):
        url = reverse("auth-signup")
        payload = {"email": "short@example.com", "password": "123"}
        response = api_client.post(url, payload, format="json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_login_success(self, api_client, patient_user):
        url = reverse("auth-login")
        payload = {"email": "patient@example.com", "password": "ValidPassword123!"}
        response = api_client.post(url, payload, format="json")

        assert response.status_code == status.HTTP_200_OK
        assert "access" in response.data
        assert "refresh" in response.data
        assert response.data["user"]["email"] == "patient@example.com"

    def test_login_wrong_password_anti_enumeration(self, api_client, patient_user):
        url = reverse("auth-login")
        payload = {"email": "patient@example.com", "password": "WrongPassword!"}
        response = api_client.post(url, payload, format="json")

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert response.data["error"]["code"] == "AUTHENTICATION_FAILED"

    def test_login_unknown_email_anti_enumeration(self, api_client):
        url = reverse("auth-login")
        payload = {"email": "nonexistent@example.com", "password": "AnyPassword123!"}
        response = api_client.post(url, payload, format="json")

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert response.data["error"]["code"] == "AUTHENTICATION_FAILED"

    def test_login_inactive_user_rejected(self, api_client, patient_user):
        patient_user.is_active = False
        patient_user.save()

        url = reverse("auth-login")
        payload = {"email": "patient@example.com", "password": "ValidPassword123!"}
        response = api_client.post(url, payload, format="json")

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_refresh_token_flow(self, api_client, patient_user):
        # First obtain token pair
        login_url = reverse("auth-login")
        login_resp = api_client.post(
            login_url,
            {"email": "patient@example.com", "password": "ValidPassword123!"},
            format="json",
        )
        refresh_token = login_resp.data["refresh"]

        # Exchange refresh token for new access token
        refresh_url = reverse("auth-refresh")
        refresh_resp = api_client.post(refresh_url, {"refresh": refresh_token}, format="json")

        assert refresh_resp.status_code == status.HTTP_200_OK
        assert "access" in refresh_resp.data

    def test_refresh_with_invalid_token(self, api_client):
        url = reverse("auth-refresh")
        response = api_client.post(url, {"refresh": "invalid-token"}, format="json")

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_protected_endpoint_without_token_rejected(self, api_client):
        url = reverse("booking-list-create")
        response = api_client.get(url)

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert response.data["error"]["code"] == "AUTHENTICATION_FAILED"
