"""API serializers for nautobot_ssot."""

from nautobot.apps.api import NautobotModelSerializer, TaggedModelSerializerMixin

from nautobot_ssot import models


class SyncSerializer(NautobotModelSerializer, TaggedModelSerializerMixin):  # pylint: disable=too-many-ancestors
    """Sync Serializer."""

    class Meta:
        """Meta attributes."""

        model = models.Sync
        fields = "__all__"

        # Option for disabling write for certain fields:
        # read_only_fields = []
