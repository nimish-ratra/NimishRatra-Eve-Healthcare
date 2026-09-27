"""
Root URL Configuration for EVE Healthcare API.
"""

from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)

from common.views import HealthLiveView, HealthReadyView

urlpatterns = [
    # Admin Panel
    path("admin/", admin.site.urls),
    # Operational Health Endpoints
    path("health/live/", HealthLiveView.as_view(), name="health-live"),
    path("health/ready/", HealthReadyView.as_view(), name="health-ready"),
    # OpenAPI Schema & Documentation
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("api/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
    # Version 1 API Routes
    path("api/v1/auth/", include("accounts.urls")),
    path("api/v1/centres/", include("catalog.urls")),
    path("api/v1/bookings/", include("bookings.urls")),
    path("api/v1/payments/", include("payments.urls")),
]
