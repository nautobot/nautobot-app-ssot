"""API views for nautobot_ssot vsphere."""

from nautobot.apps.api import NautobotModelViewSet

from nautobot_ssot.integrations.vsphere.filters import SSOTvSphereConfigFilterSet
from nautobot_ssot.integrations.vsphere.models import SSOTvSphereConfig

from .serializers import SSOTvSphereConfigSerializer


class SSOTvSphereConfigView(NautobotModelViewSet):  # pylint: disable=too-many-ancestors
    """API CRUD operations set for the SSOTvSphereConfig view."""

    queryset = SSOTvSphereConfig.objects.all()
    filterset_class = SSOTvSphereConfigFilterSet
    serializer_class = SSOTvSphereConfigSerializer
