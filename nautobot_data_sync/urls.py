"""Django urlpatterns declaration for nautobot_data_sync plugin."""

from django.urls import path

from nautobot.extras.views import ObjectChangeLogView

from . import models, views

urlpatterns = [
    path("syncs/", views.SyncListView.as_view(), name="sync_list"),
    path("syncs/start/<str:sync_worker_slug>/", views.SyncCreateView.as_view(), name="sync_add"),
    path("syncs/delete/", views.SyncBulkDeleteView.as_view(), name="sync_bulk_delete"),
    path("syncs/<uuid:pk>/", views.SyncView.as_view(), name="sync"),
    path(
        "syncs/<uuid:pk>/changelog/",
        ObjectChangeLogView.as_view(),
        name="sync_changelog",
        kwargs={"model": models.Sync},
    ),
    path("syncs/<uuid:pk>/delete/", views.SyncDeleteView.as_view(), name="sync_delete"),
    path("logs/", views.SyncLogEntryListView.as_view(), name="synclogentry_list"),
]
