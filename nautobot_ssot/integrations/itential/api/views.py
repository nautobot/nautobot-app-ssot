"""Itential SSoT API Views."""

from nautobot.apps.api import NautobotModelViewSet

from nautobot_ssot.integrations.itential import models, filters
from nautobot_ssot.integrations.itential.api import serializers


class AutomationGatewayModelViewSet(NautobotModelViewSet):  # pylint: disable=too-many-ancestors
    """AutomationGatewayModel API ViewSet."""

    queryset = models.AutomationGatewayModel.objects.all()
    serializer_class = serializers.AutomationGatewayModelSerializer
    filterset_class = filters.AutomationGatewayModelFilterSet
