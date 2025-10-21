"""Django urlpatterns declaration for nautobot_ssot app."""

from django.templatetags.static import static
from django.urls import path
from django.views.generic import RedirectView
from nautobot.apps.urls import NautobotUIViewSetRouter

from . import views
from .integrations.utils import each_enabled_integration_module

app_name = "nautobot_ssot"
router = NautobotUIViewSetRouter()
router.register("history", views.SyncUIViewSet)
router.register("logs", views.SyncLogEntryUIViewSet)

urlpatterns = [
    path("", views.DashboardView.as_view(), name="dashboard"),
    path("data-sources/<path:class_path>/", views.DataSourceTargetView.as_view(), name="data_source"),
    path("data-targets/<path:class_path>/", views.DataSourceTargetView.as_view(), name="data_target"),
    path("config/", views.SSOTConfigView.as_view(), name="config"),
    path("docs/", RedirectView.as_view(url=static("nautobot_ssot/docs/index.html")), name="docs"),
]


def _add_integrations():
    for module in each_enabled_integration_module("urls"):
        urlpatterns.extend(module.urlpatterns)


_add_integrations()

urlpatterns += router.urls
