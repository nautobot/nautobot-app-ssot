"""API serializers for OpenShift integration."""
from nautobot.apps.api import NautobotModelSerializer
from nautobot_ssot.integrations.openshift.models import SSOTOpenshiftConfig


class SSOTOpenshiftConfigSerializer(NautobotModelSerializer):
    """Serializer for SSOTOpenshiftConfig model."""
    
    class Meta:
        """Meta class for serializer."""
        model = SSOTOpenshiftConfig
        fields = "__all__"
        extra_kwargs = {
            "api_token": {"write_only": True},
        }
