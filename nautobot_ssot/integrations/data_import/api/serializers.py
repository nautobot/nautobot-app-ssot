"""API serializers for the Data Import integration."""

from nautobot.apps.api import NautobotModelSerializer

from nautobot_ssot.integrations.data_import.models import ImportPlan


class ImportPlanSerializer(NautobotModelSerializer):
    """Serializer for ImportPlan."""

    class Meta:
        """Meta class."""

        model = ImportPlan
        fields = "__all__"
