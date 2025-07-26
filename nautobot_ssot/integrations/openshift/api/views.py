"""API views for OpenShift integration."""
from nautobot.apps.api import NautobotModelViewSet
from nautobot_ssot.integrations.openshift.api.serializers import SSOTOpenshiftConfigSerializer
from nautobot_ssot.integrations.openshift.filters import SSOTOpenshiftConfigFilterSet
from nautobot_ssot.integrations.openshift.models import SSOTOpenshiftConfig


class SSOTOpenshiftConfigViewSet(NautobotModelViewSet):
    """ViewSet for SSOTOpenshiftConfig model."""
    
    queryset = SSOTOpenshiftConfig.objects.all()
    serializer_class = SSOTOpenshiftConfigSerializer
    filterset_class = SSOTOpenshiftConfigFilterSet
