"""Views for SSoT APIs."""
from rest_framework.routers import APIRootView

from nautobot.extras.api.views import NautobotModelViewSet

from nautobot_ssot.api import serializers
from nautobot_ssot import filters
from nautobot_ssot import models


class SsotRootView(APIRootView):
    """SSoT API root view."""

    def get_view_name(self):
        """API for SSoT root view boilerplate."""
        return "Single Source of Truth"


class SyncViewSet(NautobotModelViewSet):  # pylint: disable=too-many-ancestors
    """API viewset for interacting with Sync objects."""

    queryset = models.Sync.objects.all()
    serializer_class = serializers.SyncListSerializer
    filterset_class = filters.SyncFilterSet


class SyncLogEntryViewSet(NautobotModelViewSet):  # pylint: disable=too-many-ancestors
    """API viewset for interacting with SyncLogEntry objects."""

    queryset = models.SyncLogEntry.objects.all()
    serializer_class = serializers.SyncLogEntrySerializer
    filterset_class = filters.SyncLogEntryFilterSet
