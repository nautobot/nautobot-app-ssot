"""URL patterns for nautobot-ssot-servicenow."""

from django.urls import path

from . import views

urlpatterns = [
    path("servicenow/config/", views.SSOTServiceNowConfigView.as_view(), name="servicenow_config"),
]
