"""Django API serializers for nautobot_ssot app."""

from nautobot.apps.api import NautobotModelSerializer

from nautobot_ssot import models


class SyncSerializer(NautobotModelSerializer):  # pylint: disable=too-many-ancestors
    """Sync Serializer."""

    class Meta:
        """Meta attributes."""

        model = models.Sync
        fields = "__all__"


class SyncLogEntrySerializer(NautobotModelSerializer):  # pylint: disable=too-many-ancestors
    """SyncLogEntry Serializer."""

    class Meta:
        """Meta attributes."""

        model = models.SyncLogEntry
        fields = "__all__"
