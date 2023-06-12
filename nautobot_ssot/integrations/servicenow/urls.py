"""URL patterns for nautobot-ssot-servicenow."""
from django.urls import path

from . import views

app_name = "nautobot_ssot_servicenow"

urlpatterns = [
    path("config/", views.SSOTServiceNowConfigView.as_view(), name="config"),
]
