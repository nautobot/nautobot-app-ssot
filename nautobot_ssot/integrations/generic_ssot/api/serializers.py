"""API serializers for Generic SSoT Integration."""

from nautobot.apps.api import NautobotModelSerializer

from nautobot_ssot.integrations.generic_ssot.models import (
    SSOTDataSample,
    SSOTEndpoint,
    SSOTEndpointJoin,
    SSOTFieldMapping,
    SSOTSyncConfig,
    SSOTSyncConfigEndpoint,
    SSOTValueMap,
)


class SSOTEndpointSerializer(NautobotModelSerializer):
    """REST API serializer for SSOTEndpoint records."""

    class Meta:
        """Meta attributes."""

        model = SSOTEndpoint
        fields = "__all__"


class SSOTSyncConfigSerializer(NautobotModelSerializer):
    """REST API serializer for SSOTSyncConfig records."""

    class Meta:
        """Meta attributes."""

        model = SSOTSyncConfig
        fields = "__all__"


class SSOTSyncConfigEndpointSerializer(NautobotModelSerializer):
    """REST API serializer for SSOTSyncConfigEndpoint records."""

    class Meta:
        """Meta attributes."""

        model = SSOTSyncConfigEndpoint
        fields = "__all__"


class SSOTFieldMappingSerializer(NautobotModelSerializer):
    """REST API serializer for SSOTFieldMapping records."""

    class Meta:
        """Meta attributes."""

        model = SSOTFieldMapping
        fields = "__all__"


class SSOTValueMapSerializer(NautobotModelSerializer):
    """REST API serializer for SSOTValueMap records."""

    class Meta:
        """Meta attributes."""

        model = SSOTValueMap
        fields = "__all__"


class SSOTEndpointJoinSerializer(NautobotModelSerializer):
    """REST API serializer for SSOTEndpointJoin records."""

    class Meta:
        """Meta attributes."""

        model = SSOTEndpointJoin
        fields = "__all__"


class SSOTDataSampleSerializer(NautobotModelSerializer):
    """REST API serializer for SSOTDataSample records."""

    class Meta:
        """Meta attributes."""

        model = SSOTDataSample
        fields = "__all__"
