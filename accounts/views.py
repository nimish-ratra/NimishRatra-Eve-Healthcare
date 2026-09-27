"""
Authentication HTTP Views:
- POST /api/v1/auth/signup/
- POST /api/v1/auth/login/
- POST /api/v1/auth/refresh/
"""

from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenRefreshView

from accounts.serializers import (
    LoginRequestSerializer,
    SignupRequestSerializer,
    TokenResponseSerializer,
    UserResponseSerializer,
)
from accounts.services import authenticate_user, register_user
from common.throttling import AuthRateThrottle


class SignupView(APIView):
    """Endpoint for new patient account registration."""

    permission_classes = [AllowAny]
    throttle_classes = [AuthRateThrottle]

    @extend_schema(
        summary="Patient Account Signup",
        description="Creates a new patient account with a unique email address and secure password.",
        request=SignupRequestSerializer,
        responses={201: UserResponseSerializer},
    )
    def post(self, request):
        serializer = SignupRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = register_user(
            email=serializer.validated_data["email"],
            password=serializer.validated_data["password"],
        )

        response_data = UserResponseSerializer(user).data
        return Response(response_data, status=status.HTTP_201_CREATED)


class LoginView(APIView):
    """Endpoint to authenticate email and password, issuing JWT access and refresh tokens."""

    permission_classes = [AllowAny]
    throttle_classes = [AuthRateThrottle]

    @extend_schema(
        summary="User Login",
        description="Verifies credentials and returns access and refresh JWT tokens.",
        request=LoginRequestSerializer,
        responses={200: TokenResponseSerializer},
    )
    def post(self, request):
        serializer = LoginRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user, access_token, refresh_token = authenticate_user(
            email=serializer.validated_data["email"],
            password=serializer.validated_data["password"],
        )

        response_data = {
            "access": access_token,
            "refresh": refresh_token,
            "user": UserResponseSerializer(user).data,
        }
        return Response(response_data, status=status.HTTP_200_OK)


class CustomTokenRefreshView(TokenRefreshView):
    """Endpoint to exchange a valid refresh token for a new short-lived access token."""

    throttle_classes = [AuthRateThrottle]

    @extend_schema(
        summary="Refresh Access Token",
        description="Takes a valid refresh JWT token and returns a new access token.",
    )
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)
