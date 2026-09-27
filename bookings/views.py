"""
Booking HTTP Views:
- POST /api/v1/bookings/ : Create booking with authoritative price snapshot (authenticated)
- GET /api/v1/bookings/ : List caller's bookings (authenticated, isolated)
- GET /api/v1/bookings/{id}/ : Get booking details (authenticated, ownership isolated)
- POST /api/v1/bookings/{id}/cancel/ : Cancel booking with row lock serialization (authenticated)
"""

import uuid

from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from bookings.selectors import get_user_booking_by_id, list_user_bookings
from bookings.serializers import (
    BookingCreateRequestSerializer,
    BookingResponseSerializer,
)
from bookings.services import cancel_booking, create_booking
from common.pagination import StandardResultsSetPagination


class BookingListCreateView(APIView):
    """List caller's bookings or create a new booking with an authoritative price snapshot."""

    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination

    @extend_schema(
        summary="List User Bookings",
        description="Returns a paginated list of all bookings belonging strictly to the authenticated patient.",
        responses={200: BookingResponseSerializer(many=True)},
    )
    def get(self, request):
        bookings = list_user_bookings(user=request.user)
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(bookings, request)
        serializer = BookingResponseSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    @extend_schema(
        summary="Create Diagnostic Booking",
        description=(
            "Book an appointment for a specific centre test offering. "
            "The client does not supply the price; the server authoritatively snapshots the offering price."
        ),
        request=BookingCreateRequestSerializer,
        responses={201: BookingResponseSerializer},
    )
    def post(self, request):
        serializer = BookingCreateRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        booking = create_booking(
            user=request.user,
            centre_test_id=serializer.validated_data["centre_test_id"],
            appointment_at=serializer.validated_data["appointment_at"],
        )
        return Response(
            BookingResponseSerializer(booking).data,
            status=status.HTTP_201_CREATED,
        )


class BookingDetailView(APIView):
    """Retrieve details for a single booking owned by the authenticated patient."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Get Booking Details",
        description="Retrieves a specific booking. If the booking belongs to another patient, 404 is returned.",
        responses={200: BookingResponseSerializer},
    )
    def get(self, request, id: uuid.UUID):
        booking = get_user_booking_by_id(booking_id=id, user=request.user)
        return Response(BookingResponseSerializer(booking).data, status=status.HTTP_200_OK)


class BookingCancelView(APIView):
    """Cancel a booking owned by the caller using transactional row locking."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Cancel Booking",
        description="Cancels an existing booking. Transitions state safely under concurrency.",
        request=None,
        responses={200: BookingResponseSerializer},
    )
    def post(self, request, id: uuid.UUID):
        booking = cancel_booking(booking_id=id, user=request.user)
        return Response(BookingResponseSerializer(booking).data, status=status.HTTP_200_OK)
