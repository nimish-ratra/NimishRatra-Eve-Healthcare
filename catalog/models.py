"""
Catalog Domain Models:
- DiagnosticCentre: Physical facility offering services.
- DiagnosticTest: Reusable diagnostic test definition.
- CentreTest: Specific offering connecting a Centre with a Test and setting authoritative Price.
"""

import uuid
from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models


class DiagnosticCentre(models.Model):
    """Physical diagnostic laboratory or scan center."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255, db_index=True)
    location = models.CharField(max_length=255, db_index=True)
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "diagnostic_centres"
        verbose_name = "diagnostic centre"
        verbose_name_plural = "diagnostic centres"
        ordering = ["name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.location})"


class DiagnosticTest(models.Model):
    """Canonical, reusable medical diagnostic test item (e.g. MRI Brain, CBC, Lipid Profile)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=50, unique=True, db_index=True)
    name = models.CharField(max_length=255, db_index=True)
    description = models.TextField(blank=True, default="")
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "diagnostic_tests"
        verbose_name = "diagnostic test"
        verbose_name_plural = "diagnostic tests"
        ordering = ["name"]

    def __str__(self) -> str:
        return f"{self.name} [{self.code}]"


class CentreTest(models.Model):
    """Centre-specific offering of a test with authoritative pricing."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    centre = models.ForeignKey(
        DiagnosticCentre,
        on_delete=models.PROTECT,
        related_name="offerings",
    )
    test = models.ForeignKey(
        DiagnosticTest,
        on_delete=models.PROTECT,
        related_name="centre_offerings",
    )
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
        help_text="Authoritative offering price in INR.",
    )
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "centre_tests"
        verbose_name = "centre test offering"
        verbose_name_plural = "centre test offerings"
        constraints = [
            models.UniqueConstraint(
                fields=["centre", "test"],
                name="unique_centre_test_offering",
            ),
            models.CheckConstraint(
                condition=models.Q(price__gt=0),
                name="positive_centre_test_price",
            ),
        ]
        ordering = ["test__name"]

    def __str__(self) -> str:
        return f"{self.centre.name} - {self.test.name} (₹{self.price})"
