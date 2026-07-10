"""Filters for the Data Import integration."""

from nautobot.apps.filters import NautobotFilterSet, SearchFilter

from nautobot_ssot.integrations.data_import.models import ImportPlan


class ImportPlanFilterSet(NautobotFilterSet):
    """FilterSet for ImportPlan."""

    q = SearchFilter(filter_predicates={"name": "icontains", "description": "icontains"})

    class Meta:
        """Meta class."""

        model = ImportPlan
        fields = ["id", "name", "integration", "enabled"]
