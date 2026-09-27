"""
Catalog HTTP Views:
- GET /api/v1/centres/ : Browse active diagnostic centres (public, filterable by location)
- POST /api/v1/centres/ : Create diagnostic centre (admin only)
- GET /api/v1/centres/{id}/tests/ : List active test offerings and prices for a centre (public)
- POST /api/v1/centres/{id}/tests/ : Add offering to centre with authoritative price (admin only)
- POST /api/v1/centres/tests/ : Register a new canonical diagnostic test (admin only)
"""

import uuid

from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from catalog.selectors import (
    get_centre_by_id,
    list_active_centre_offerings,
    list_active_centres,
)
from catalog.serializers import (
    CentreTestCreateSerializer,
    CentreTestSummarySerializer,
    DiagnosticCentreCreateSerializer,
    DiagnosticCentreSerializer,
    DiagnosticTestCreateSerializer,
    DiagnosticTestSerializer,
)
from catalog.services import (
    create_centre,
    create_centre_offering,
    create_diagnostic_test,
)
from common.pagination import StandardResultsSetPagination
from common.permissions import IsAdminUserRole


class DiagnosticCentreListCreateView(APIView):
    """List diagnostic centres (public) or register a new centre (admin only)."""

    pagination_class = StandardResultsSetPagination

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsAdminUserRole()]
        return [AllowAny()]

    @extend_schema(
        summary="Browse Diagnostic Centres",
        description="Public paginated endpoint to list active diagnostic centres, optionally filtering by location.",
        parameters=[
            OpenApiParameter(
                name="location",
                type=str,
                location=OpenApiParameter.QUERY,
                description="Case-insensitive location filter (e.g. Gurugram, Mumbai).",
                required=False,
            ),
        ],
        responses={200: DiagnosticCentreSerializer(many=True)},
    )
    def get(self, request):
        location = request.query_params.get("location")
        centres = list_active_centres(location=location)

        paginator = self.pagination_class()
        page = paginator.paginate_queryset(centres, request)
        serializer = DiagnosticCentreSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    @extend_schema(
        summary="Create Diagnostic Centre",
        description="Admin-only endpoint to register a new diagnostic laboratory.",
        request=DiagnosticCentreCreateSerializer,
        responses={201: DiagnosticCentreSerializer},
    )
    def post(self, request):
        serializer = DiagnosticCentreCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        centre = create_centre(
            name=serializer.validated_data["name"],
            location=serializer.validated_data["location"],
        )
        return Response(
            DiagnosticCentreSerializer(centre).data,
            status=status.HTTP_201_CREATED,
        )


class CentreTestOfferingListView(APIView):
    """Retrieve or register test offerings with authoritative pricing for a specific centre."""

    pagination_class = StandardResultsSetPagination

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsAdminUserRole()]
        return [AllowAny()]

    @extend_schema(
        summary="List Centre Offerings & Pricing",
        description="Public endpoint returning all active diagnostic tests offered by a centre with their authoritative prices.",
        responses={200: CentreTestSummarySerializer(many=True)},
    )
    def get(self, request, id: uuid.UUID):
        # Validates centre existence
        get_centre_by_id(id)
        offerings = list_active_centre_offerings(centre_id=id)

        paginator = self.pagination_class()
        page = paginator.paginate_queryset(offerings, request)
        serializer = CentreTestSummarySerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    @extend_schema(
        operation_id="add_centre_offering",
        summary="Add Offering to Centre",
        description="Admin-only endpoint to offer a diagnostic test at a centre with an authoritative price.",
        request=CentreTestCreateSerializer,
        responses={201: CentreTestSummarySerializer},
    )
    def post(self, request, id: uuid.UUID):
        serializer = CentreTestCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        offering = create_centre_offering(
            centre_id=id,
            test_id=serializer.validated_data["test_id"],
            price=serializer.validated_data["price"],
        )
        return Response(
            CentreTestSummarySerializer(offering).data,
            status=status.HTTP_201_CREATED,
        )


class DiagnosticTestCreateView(APIView):
    """Admin-only endpoint to register a reusable canonical diagnostic test."""

    permission_classes = [IsAdminUserRole]

    @extend_schema(
        operation_id="register_canonical_diagnostic_test",
        summary="Register Diagnostic Test",
        description="Admin-only endpoint to define a new reusable medical test (e.g. MRI Brain, CBC).",
        request=DiagnosticTestCreateSerializer,
        responses={201: DiagnosticTestSerializer},
    )
    def post(self, request):
        serializer = DiagnosticTestCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        test = create_diagnostic_test(
            code=serializer.validated_data["code"],
            name=serializer.validated_data["name"],
            description=serializer.validated_data.get("description", ""),
        )
        return Response(
            DiagnosticTestSerializer(test).data,
            status=status.HTTP_201_CREATED,
        )
