"""API serializers for nautobot_ssot Proxmox VE."""

from nautobot.apps.api import NautobotModelSerializer

from nautobot_ssot.integrations.proxmox.models import SSOTProxmoxConfig


class SSOTProxmoxConfigSerializer(NautobotModelSerializer):  # pylint: disable=too-many-ancestors
    """REST API serializer for SSOTProxmoxConfig records."""

    class Meta:
        """Meta attributes."""

        model = SSOTProxmoxConfig
        fields = "__all__"
