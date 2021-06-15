"""Django urlpatterns declaration for nautobot_ssot plugin."""

from django.urls import path

from . import models, views

urlpatterns = [
    path("", views.DashboardView.as_view(), name="dashboard"),
    path("history/", views.SyncListView.as_view(), name="sync_list"),
    path("history/delete/", views.SyncBulkDeleteView.as_view(), name="sync_bulk_delete"),
    path("history/<uuid:pk>/", views.SyncView.as_view(), name="sync"),
    path(
        "history/<uuid:pk>/changelog/",
        views.SyncChangeLogView.as_view(),
        name="sync_changelog",
        kwargs={"model": models.Sync},
    ),
    path("history/<uuid:pk>/delete/", views.SyncDeleteView.as_view(), name="sync_delete"),
    path("history/<uuid:pk>/jobresult/", views.SyncJobResultView.as_view(), name="sync_jobresult"),
    path("history/<uuid:pk>/logs/", views.SyncLogEntriesView.as_view(), name="sync_logentries"),
    path("logs/", views.SyncLogEntryListView.as_view(), name="synclogentry_list"),
]
