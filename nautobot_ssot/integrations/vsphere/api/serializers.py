"""API serializers for nautobot_ssot vsphere."""

from nautobot.apps.api import NautobotModelSerializer

from nautobot_ssot.integrations.vsphere.models import SSOTvSphereConfig


class SSOTvSphereConfigSerializer(NautobotModelSerializer):  # pylint: disable=too-many-ancestors
    """REST API serializer for SSOTInfobloxConfig records."""

    class Meta:
        """Meta attributes."""

        model = SSOTvSphereConfig
        fields = "__all__"
