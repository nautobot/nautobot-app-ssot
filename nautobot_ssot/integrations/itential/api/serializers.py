"""Itential SSoT serializers."""

from rest_framework import serializers

from nautobot.apps.api import NautobotModelSerializer

from nautobot_ssot.integrations.itential import models


class AutomationGatewayModelSerializer(NautobotModelSerializer):
    """AutomationGatewayModel serializer."""

    url = serializers.HyperlinkedIdentityField(view_name="plugins-api:nautobot_ssot-api:automationgatewaymodel-detail")

    class Meta:
        """Meta class definition."""

        model = models.AutomationGatewayModel
        fields = "__all__"
