"""URL patterns for OpenShift integration."""
from django.urls import path
from nautobot_ssot.integrations.openshift import views

app_name = "openshift"

urlpatterns = [
    path("config/", views.SSOTOpenshiftConfigListView.as_view(), name="config_list"),
    path("config/add/", views.SSOTOpenshiftConfigEditView.as_view(), name="config_add"),
    path("config/<uuid:pk>/", views.SSOTOpenshiftConfigView.as_view(), name="config"),
    path("config/<uuid:pk>/edit/", views.SSOTOpenshiftConfigEditView.as_view(), name="config_edit"),
    path("config/<uuid:pk>/delete/", views.SSOTOpenshiftConfigDeleteView.as_view(), name="config_delete"),
    path("config/delete/", views.SSOTOpenshiftConfigBulkDeleteView.as_view(), name="config_bulk_delete"),
]
