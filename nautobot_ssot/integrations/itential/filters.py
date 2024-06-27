"""Itential SSoT Filters."""

from nautobot.apps.filters import BaseFilterSet, SearchFilter

from nautobot_ssot.integrations.itential import models


class AutomationGatewayModelFilterSet(BaseFilterSet):
    """AutomationGatewayModel FilterSet."""

    q = SearchFilter(filter_predicates={"name": "icontains"})

    class Meta:
        """Meta class definition."""

        model = models.AutomationGatewayModel
        fields = ["name"]
