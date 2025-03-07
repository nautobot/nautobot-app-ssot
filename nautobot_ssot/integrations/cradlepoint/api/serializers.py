"""API serializers for the Cradlepoint integration."""

from nautobot.apps.api import NautobotModelSerializer

from nautobot_ssot.integrations.cradlepoint.models import SSOTCradlepointConfig


class SSOTCradlepointConfigSerializer(
    NautobotModelSerializer
):  # pylint: disable=too-many-ancestors
    """REST API serializer for SSOTCradlepoint Config records."""

    class Meta:
        """Meta attributes."""

        model = SSOTCradlepointConfig
        fields = "__all__"
