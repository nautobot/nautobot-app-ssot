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
router.register("sync-records", views.SyncRecordUIViewSet)

urlpatterns = [
    path("", views.DashboardView.as_view(), name="dashboard"),
    path("data-sources/<path:class_path>/", views.DataSourceTargetView.as_view(), name="data_source"),
    path("data-targets/<path:class_path>/", views.DataSourceTargetView.as_view(), name="data_target"),
    path("config/", views.SSOTConfigView.as_view(), name="config"),
    path("docs/", RedirectView.as_view(url=static("nautobot_ssot/docs/index.html")), name="docs"),
    path("process_bulk_syncrecords/", views.process_bulk_syncrecords, name="process_bulk_syncrecords"),
    # Expanded diff view for a Sync
    path("history/<uuid:pk>/diff/", views.SyncDiffView.as_view(), name="sync_diff"),
    # Lazy-loaded expanded diff section content
    path("history/<uuid:pk>/diff-section/<path:record_type>/", views.SyncDiffSectionContentView.as_view(), name="sync_diff_section"),
    path("sync-records/<uuid:pk>/history/", views.SyncedObjectHistoryView.as_view(), name="syncrecord_history"),
]


def _add_integrations():
    for module in each_enabled_integration_module("urls"):
        urlpatterns.extend(module.urlpatterns)


_add_integrations()

urlpatterns += router.urls
