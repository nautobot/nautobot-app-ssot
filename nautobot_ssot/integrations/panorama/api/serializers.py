"""Plugin API serializers."""

from nautobot.apps.api import NautobotModelSerializer

from nautobot_ssot.integrations.panorama.models import LogicalGroup, VirtualSystem


class VirtualSystemSerializer(NautobotModelSerializer):  # pylint: disable=too-many-ancestors
    """Used for normal CRUD operations."""

    # url = serializers.HyperlinkedIdentityField(view_name="plugins-api:nautobot_ssot_panorama-api:virtualsystem-detail")
    # device = Device
    # interfaces = Interface

    class Meta:
        """Meta class."""

        model = VirtualSystem
        fields = "__all__"


class LogicalGroupSerializer(NautobotModelSerializer):  # pylint: disable=too-many-ancestors
    """Used for normal CRUD operations."""

    # url = serializers.HyperlinkedIdentityField(view_name="plugins-api:nautobot_ssot_panorama-api:logicalgroup-detail")

    class Meta:
        """Meta class."""

        model = LogicalGroup
        fields = "__all__"
