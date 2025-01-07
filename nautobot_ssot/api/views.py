"""API views for nautobot_ssot."""

from nautobot.apps.api import NautobotModelViewSet

from nautobot_ssot import filters, models
from nautobot_ssot.api import serializers


class SyncViewSet(NautobotModelViewSet):  # pylint: disable=too-many-ancestors
    """Sync viewset."""

    queryset = models.Sync.objects.all()
    serializer_class = serializers.SyncSerializer
    filterset_class = filters.SyncFilterSet

    # Option for modifying the default HTTP methods:
    # http_method_names = ["get", "post", "put", "patch", "delete", "head", "options", "trace"]
