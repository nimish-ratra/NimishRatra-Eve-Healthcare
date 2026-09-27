from django.urls import path

from catalog.views import (
    CentreTestOfferingListView,
    DiagnosticCentreListCreateView,
    DiagnosticTestCreateView,
)

urlpatterns = [
    path("", DiagnosticCentreListCreateView.as_view(), name="centre-list-create"),
    path("tests/", DiagnosticTestCreateView.as_view(), name="test-create"),
    path("<uuid:id>/tests/", CentreTestOfferingListView.as_view(), name="centre-offerings"),
]
