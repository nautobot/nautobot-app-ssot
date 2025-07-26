"""API serializers for OpenShift integration."""
from rest_framework import serializers
from nautobot.core.api.serializers import ValidatedModelSerializer
from nautobot_ssot.integrations.openshift.models import SSOTOpenshiftConfig


class SSOTOpenshiftConfigSerializer(ValidatedModelSerializer):
    """Serializer for SSOTOpenshiftConfig model."""
    
    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:nautobot_ssot-api:openshift-config-detail"
    )
    
    class Meta:
        """Meta class for serializer."""
        model = SSOTOpenshiftConfig
        fields = "__all__"
        extra_kwargs = {
            "api_token": {"write_only": True},
        }
