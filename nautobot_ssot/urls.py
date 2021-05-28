"""Django urlpatterns declaration for nautobot_ssot plugin."""

from django.urls import path

from nautobot.extras.views import ObjectChangeLogView

from . import models, views

urlpatterns = [
    path("sync/<str:sync_worker_slug>/", views.SyncCreateView.as_view(), name="sync_add"),
    path("history/", views.SyncListView.as_view(), name="sync_list"),
    path("history/delete/", views.SyncBulkDeleteView.as_view(), name="sync_bulk_delete"),
    path("history/<uuid:pk>/", views.SyncView.as_view(), name="sync"),
    path(
        "history/<uuid:pk>/changelog/",
        ObjectChangeLogView.as_view(),
        name="sync_changelog",
        kwargs={"model": models.Sync},
    ),
    path("history/<uuid:pk>/delete/", views.SyncDeleteView.as_view(), name="sync_delete"),
    path("logs/", views.SyncLogEntryListView.as_view(), name="synclogentry_list"),
]
