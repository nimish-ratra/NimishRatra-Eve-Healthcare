"""
Catalog Services:
Admin catalogue mutations (centre creation, test creation, offering assignment, and soft deactivation).
"""

import uuid
from decimal import Decimal

from django.db import IntegrityError, transaction

from catalog.models import CentreTest, DiagnosticCentre, DiagnosticTest
from common.exceptions import ConflictError, NotFoundError, ValidationError


def create_centre(name: str, location: str) -> DiagnosticCentre:
    """Creates a new diagnostic centre."""
    name_clean = name.strip()
    loc_clean = location.strip()
    if not name_clean or not loc_clean:
        raise ValidationError("Centre name and location are required.")

    return DiagnosticCentre.objects.create(name=name_clean, location=loc_clean, is_active=True)


def create_diagnostic_test(code: str, name: str, description: str = "") -> DiagnosticTest:
    """Creates a reusable diagnostic test."""
    code_clean = code.strip().upper()
    name_clean = name.strip()
    if not code_clean or not name_clean:
        raise ValidationError("Diagnostic test code and name are required.")

    try:
        return DiagnosticTest.objects.create(
            code=code_clean,
            name=name_clean,
            description=description.strip(),
            is_active=True,
        )
    except IntegrityError as err:
        raise ConflictError(f"A diagnostic test with code '{code_clean}' already exists.") from err


def create_centre_offering(centre_id: uuid.UUID, test_id: uuid.UUID, price: Decimal) -> CentreTest:
    """Binds a test to a centre with an authoritative price.
    Enforces UNIQUE(centre, test) and price > 0.
    """
    try:
        centre = DiagnosticCentre.objects.get(id=centre_id)
    except DiagnosticCentre.DoesNotExist as err:
        raise NotFoundError("Diagnostic centre does not exist.") from err

    try:
        test = DiagnosticTest.objects.get(id=test_id)
    except DiagnosticTest.DoesNotExist as err:
        raise NotFoundError("Diagnostic test does not exist.") from err

    if price <= Decimal("0.00"):
        raise ValidationError("Price must be greater than zero.")

    try:
        with transaction.atomic():
            return CentreTest.objects.create(
                centre=centre,
                test=test,
                price=price,
                is_active=True,
            )
    except IntegrityError as err:
        raise ConflictError(
            f"Centre '{centre.name}' already offers '{test.name}'. Update existing offering instead."
        ) from err


def soft_deactivate_centre(centre_id: uuid.UUID) -> DiagnosticCentre:
    """Soft deactivates a diagnostic centre.
    Historical bookings reference preserved; new bookings prohibited.
    """
    try:
        centre = DiagnosticCentre.objects.get(id=centre_id)
    except DiagnosticCentre.DoesNotExist as err:
        raise NotFoundError("Diagnostic centre not found.") from err

    centre.is_active = False
    centre.save(update_fields=["is_active", "updated_at"])
    return centre


def soft_deactivate_offering(centre_test_id: uuid.UUID) -> CentreTest:
    """Soft deactivates a centre test offering."""
    try:
        offering = CentreTest.objects.get(id=centre_test_id)
    except CentreTest.DoesNotExist as err:
        raise NotFoundError("Offering not found.") from err

    offering.is_active = False
    offering.save(update_fields=["is_active", "updated_at"])
    return offering
