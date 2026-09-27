"""
Authorization Permissions:
- IsAdminUserRole: Ensures the caller is authenticated AND has is_admin=True.
- IsBookingOwner: Ensures a booking can only be viewed or modified by its owner.
"""

from rest_framework import permissions


class IsAdminUserRole(permissions.BasePermission):
    """Allows access only to authenticated users marked with is_admin=True."""

    message = "Administrator privileges are required to perform this action."

    def has_permission(self, request, view) -> bool:
        return bool(
            request.user
            and request.user.is_authenticated
            and getattr(request.user, "is_admin", False)
        )


class IsBookingOwner(permissions.BasePermission):
    """Object-level permission ensuring only the patient who owns the booking can access it."""

    message = "You do not own this booking."

    def has_object_permission(self, request, view, obj) -> bool:
        return bool(
            request.user and request.user.is_authenticated and obj.user_id == request.user.id
        )
