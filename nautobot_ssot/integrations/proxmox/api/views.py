"""API views for nautobot_ssot Proxmox VE."""

from nautobot.apps.api import NautobotModelViewSet

from nautobot_ssot.integrations.proxmox.filters import SSOTProxmoxConfigFilterSet
from nautobot_ssot.integrations.proxmox.models import SSOTProxmoxConfig

from .serializers import SSOTProxmoxConfigSerializer


class SSOTProxmoxConfigView(NautobotModelViewSet):  # pylint: disable=too-many-ancestors
    """API CRUD operations set for the SSOTProxmoxConfig view."""

    queryset = SSOTProxmoxConfig.objects.all()
    filterset_class = SSOTProxmoxConfigFilterSet
    serializer_class = SSOTProxmoxConfigSerializer
