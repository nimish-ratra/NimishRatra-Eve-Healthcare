"""
Deterministic Demo Data Seeder for Reviewer Evaluation.
Usage:
    python manage.py seed_demo_data
"""

import os
from decimal import Decimal

from django.core.management.base import BaseCommand

from accounts.models import User
from catalog.models import CentreTest, DiagnosticCentre, DiagnosticTest


class Command(BaseCommand):
    help = "Seeds deterministic demo data including centres, reusable tests, offerings, and sample accounts."

    def handle(self, *args, **options):
        self.stdout.write("Seeding EVE Healthcare demonstration data...")

        # 1. Seed Accounts
        admin_email = os.getenv("DEMO_ADMIN_EMAIL", "admin@evehealth.com")
        admin_password = os.getenv("DEMO_ADMIN_PASSWORD", "EveAdmin#2026!")
        admin_user, admin_created = User.objects.get_or_create(
            email=admin_email,
            defaults={"is_admin": True, "is_staff": True, "is_superuser": True},
        )
        if admin_created:
            admin_user.set_password(admin_password)
            admin_user.save()
            self.stdout.write(self.style.SUCCESS(f"Created Admin account: {admin_email}"))
        else:
            self.stdout.write(f"Admin account already exists: {admin_email}")

        patient_email = os.getenv("DEMO_PATIENT_EMAIL", "patient@evehealth.com")
        patient_password = os.getenv("DEMO_PATIENT_PASSWORD", "EvePatient#2026!")
        patient_user, patient_created = User.objects.get_or_create(
            email=patient_email,
            defaults={"is_admin": False},
        )
        if patient_created:
            patient_user.set_password(patient_password)
            patient_user.save()
            self.stdout.write(self.style.SUCCESS(f"Created Demo Patient account: {patient_email}"))
        else:
            self.stdout.write(f"Patient account already exists: {patient_email}")

        # 2. Seed Diagnostic Centres
        centres_data = [
            ("EVE Diagnostics Central - Gurugram", "Sector 44, Gurugram, Haryana"),
            ("EVE Health Labs - South Delhi", "Hauz Khas, New Delhi"),
            ("Apex Care Diagnostics - Bengaluru", "Indiranagar, Bengaluru, Karnataka"),
        ]
        centres = {}
        for name, location in centres_data:
            centre, _ = DiagnosticCentre.objects.get_or_create(
                name=name,
                defaults={"location": location, "is_active": True},
            )
            centres[name] = centre

        self.stdout.write(f"Created/verified {len(centres)} diagnostic centres.")

        # 3. Seed Canonical Diagnostic Tests
        tests_data = [
            (
                "MRI_BRAIN",
                "MRI Brain with Contrast",
                "High-field magnetic resonance neuro-imaging scan.",
            ),
            ("CBC", "Complete Blood Count (CBC)", "Automated 24-parameter complete blood count."),
            (
                "LIPID_PROFILE",
                "Comprehensive Lipid Profile",
                "Total cholesterol, HDL, LDL, VLDL, and triglycerides.",
            ),
            (
                "THYROID_TSH",
                "Thyroid Stimulating Hormone (TSH)",
                "High-sensitivity chemiluminescence immunoassay.",
            ),
            (
                "VIT_D3",
                "Vitamin D3 (25-Hydroxy)",
                "Quantitative assessment of 25-OH Vitamin D serum level.",
            ),
        ]
        tests = {}
        for code, name, desc in tests_data:
            test, _ = DiagnosticTest.objects.get_or_create(
                code=code,
                defaults={"name": name, "description": desc, "is_active": True},
            )
            tests[code] = test

        self.stdout.write(f"Created/verified {len(tests)} diagnostic tests.")

        # 4. Seed Centre Test Offerings with Centre-Specific Authoritative Pricing
        offerings_spec = [
            # Gurugram Offerings
            (centres["EVE Diagnostics Central - Gurugram"], tests["MRI_BRAIN"], Decimal("3500.00")),
            (centres["EVE Diagnostics Central - Gurugram"], tests["CBC"], Decimal("450.00")),
            (
                centres["EVE Diagnostics Central - Gurugram"],
                tests["LIPID_PROFILE"],
                Decimal("800.00"),
            ),
            (centres["EVE Diagnostics Central - Gurugram"], tests["VIT_D3"], Decimal("1200.00")),
            # South Delhi Offerings (Different pricing demonstrating centre-specific model)
            (centres["EVE Health Labs - South Delhi"], tests["MRI_BRAIN"], Decimal("4200.00")),
            (centres["EVE Health Labs - South Delhi"], tests["CBC"], Decimal("500.00")),
            (centres["EVE Health Labs - South Delhi"], tests["LIPID_PROFILE"], Decimal("950.00")),
            (centres["EVE Health Labs - South Delhi"], tests["VIT_D3"], Decimal("1400.00")),
            # Bengaluru Offerings
            (centres["Apex Care Diagnostics - Bengaluru"], tests["CBC"], Decimal("420.00")),
            (centres["Apex Care Diagnostics - Bengaluru"], tests["THYROID_TSH"], Decimal("600.00")),
        ]

        count = 0
        for centre, test, price in offerings_spec:
            offering, created = CentreTest.objects.get_or_create(
                centre=centre,
                test=test,
                defaults={"price": price, "is_active": True},
            )
            if created:
                count += 1

        self.stdout.write(
            self.style.SUCCESS(f"Seeded demo offerings. Total new offerings added: {count}")
        )
        self.stdout.write(self.style.SUCCESS("Demo database setup complete!"))
