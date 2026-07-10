"""API views for the Data Import integration."""

from nautobot.apps.api import NautobotModelViewSet

from nautobot_ssot.integrations.data_import.api.serializers import ImportPlanSerializer
from nautobot_ssot.integrations.data_import.filters import ImportPlanFilterSet
from nautobot_ssot.integrations.data_import.models import ImportPlan


class ImportPlanViewSet(NautobotModelViewSet):  # pylint: disable=too-many-ancestors
    """REST viewset for ImportPlan."""

    queryset = ImportPlan.objects.all()
    serializer_class = ImportPlanSerializer
    filterset_class = ImportPlanFilterSet
