"""API views for nautobot_ssot infoblox."""

from nautobot.apps.api import NautobotModelViewSet

from nautobot_ssot.integrations.infoblox.filters import SSOTInfobloxConfigFilterSet
from nautobot_ssot.integrations.infoblox.models import SSOTInfobloxConfig
from .serializers import SSOTInfobloxConfigSerializer


class SSOTInfobloxConfigView(NautobotModelViewSet):  # pylint: disable=too-many-ancestors
    """API CRUD operations set for the SSOTInfobloxConfig view."""

    queryset = SSOTInfobloxConfig.objects.all()
    filterset_class = SSOTInfobloxConfigFilterSet
    serializer_class = SSOTInfobloxConfigSerializer
