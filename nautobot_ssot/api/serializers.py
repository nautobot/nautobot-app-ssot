"""REST API serializer capabilities for SSoT."""
from nautobot.extras.api.serializers import NautobotModelSerializer

from nautobot_ssot import models


class SyncListSerializer(NautobotModelSerializer):  # pylint: disable=abstract-method, too-many-ancestors
    """Serializer for Sync objects."""

    class Meta:
        """Set Meta Data for Sync, will serialize fields."""

        model = models.Sync
        fields = "__all__"


class SyncLogEntrySerializer(NautobotModelSerializer):  # pylint: disable=abstract-method, too-many-ancestors
    """Serializer for SyncLogEntry objects."""

    class Meta:
        """Set Meta Data for SyncLogEntry, will serialize fields."""

        model = models.SyncLogEntry
        fields = [
            "timestamp",
            "action",
            "status",
            "diff",
            "synced_object_type",
            "synced_object_id",
            "object_repr",
            "message",
        ]
