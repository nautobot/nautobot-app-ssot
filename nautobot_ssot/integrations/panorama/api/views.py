"""API views for firewall models."""

from nautobot.extras.api.views import NautobotModelViewSet

from nautobot_ssot.integrations.panorama import filters, models
from nautobot_ssot.integrations.panorama.api import serializers


class VirtualSystemViewSet(NautobotModelViewSet):  # pylint: disable=too-many-ancestors
    """VirtualSystem viewset."""

    queryset = models.VirtualSystem.objects.all()
    serializer_class = serializers.VirtualSystemSerializer
    filterset_class = filters.VirtualSystemFilterSet


class LogicalGroupViewSet(NautobotModelViewSet):  # pylint: disable=too-many-ancestors
    """LogicalGroup viewset."""

    queryset = models.LogicalGroup.objects.all()
    serializer_class = serializers.LogicalGroupSerializer
    filterset_class = filters.LogicalGroupFilterSet
