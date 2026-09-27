"""
Catalog Selectors:
Read-only query composition for diagnostic centres and offerings.
"""

import uuid

from django.db.models import QuerySet

from catalog.models import CentreTest, DiagnosticCentre
from common.exceptions import NotFoundError, OfferingUnavailableError


def list_active_centres(location: str | None = None) -> QuerySet[DiagnosticCentre]:
    """Retrieves active diagnostic centres, optionally filtering by location (case-insensitive)."""
    qs = DiagnosticCentre.objects.filter(is_active=True)
    if location:
        qs = qs.filter(location__icontains=location.strip())
    return qs.order_by("name")


def get_centre_by_id(centre_id: uuid.UUID) -> DiagnosticCentre:
    """Retrieves a diagnostic centre or raises NotFoundError."""
    try:
        return DiagnosticCentre.objects.get(id=centre_id)
    except DiagnosticCentre.DoesNotExist as err:
        raise NotFoundError("Diagnostic centre not found.") from err


def list_active_centre_offerings(centre_id: uuid.UUID) -> QuerySet[CentreTest]:
    """Retrieves all active diagnostic test offerings for a given active centre."""
    centre = get_centre_by_id(centre_id)
    if not centre.is_active:
        return CentreTest.objects.none()

    return (
        CentreTest.objects.filter(
            centre=centre,
            is_active=True,
            test__is_active=True,
        )
        .select_related("test", "centre")
        .order_by("test__name")
    )


def get_active_centre_test(centre_test_id: uuid.UUID) -> CentreTest:
    """Authoritative lookup of a CentreTest offering.
    Validates that:
    1. The CentreTest exists.
    2. The CentreTest is active.
    3. The parent DiagnosticCentre is active.
    4. The parent DiagnosticTest is active.
    Raises OfferingUnavailableError if any invariant is violated.
    """
    try:
        centre_test = CentreTest.objects.select_related("centre", "test").get(id=centre_test_id)
    except (CentreTest.DoesNotExist, ValueError) as err:
        raise OfferingUnavailableError("The specified diagnostic offering was not found.") from err

    if not centre_test.is_active:
        raise OfferingUnavailableError("This diagnostic offering has been deactivated.")

    if not centre_test.centre.is_active:
        raise OfferingUnavailableError("The diagnostic centre offering this test is inactive.")

    if not centre_test.test.is_active:
        raise OfferingUnavailableError("The diagnostic test requested is inactive.")

    return centre_test
