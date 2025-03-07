"""API views for Cradlepoint vsphere."""

from nautobot.apps.api import NautobotModelViewSet

from nautobot_ssot.integrations.cradlepoint.filters import (
    SSOTCradlepointConfigFilterSet,
)
from nautobot_ssot.integrations.cradlepoint.models import SSOTCradlepointConfig

from .serializers import SSOTCradlepointConfigSerializer


class SSOTCradlepointConfigView(
    NautobotModelViewSet
):  # pylint: disable=too-many-ancestors
    """API CRUD operations set for the SSOTvSphereConfig view."""

    queryset = SSOTCradlepointConfig.objects.all()
    filterset_class = SSOTCradlepointConfigFilterSet
    serializer_class = SSOTCradlepointConfigSerializer
