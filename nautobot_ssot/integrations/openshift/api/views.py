"""API views for OpenShift integration."""
from nautobot.apps.api import NautobotModelViewSet

from nautobot_ssot.integrations.openshift.filters import SSOTOpenshiftConfigFilterSet
from nautobot_ssot.integrations.openshift.models import SSOTOpenshiftConfig

from .serializers import SSOTOpenshiftConfigSerializer


class SSOTOpenshiftConfigViewSet(NautobotModelViewSet):
    """API CRUD operations set for the SSOTOpenshiftConfig view."""
    
    queryset = SSOTOpenshiftConfig.objects.all()
    filterset_class = SSOTOpenshiftConfigFilterSet
    serializer_class = SSOTOpenshiftConfigSerializer
