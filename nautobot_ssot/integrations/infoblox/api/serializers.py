"""API serializers for nautobot_ssot infoblox."""

from nautobot.apps.api import NautobotModelSerializer

from nautobot_ssot.integrations.infoblox.models import SSOTInfobloxConfig


class SSOTInfobloxConfigSerializer(NautobotModelSerializer):  # pylint: disable=too-many-ancestors
    """REST API serializer for SSOTInfobloxConfig records."""

    class Meta:
        """Meta attributes."""

        model = SSOTInfobloxConfig
        fields = "__all__"
