"""Itential SSoT tables."""

import django_tables2 as tables

from nautobot.apps.tables import (
    BaseTable,
    ButtonsColumn,
    ToggleColumn,
)

from nautobot_ssot.integrations.itential import models


class AutomationGatewayModelTable(BaseTable):
    """AutomationGatewayModel Table."""

    pk = ToggleColumn()
    name = tables.LinkColumn()
    actions = ButtonsColumn(models.AutomationGatewayModel)

    class Meta:
        """Meta class definition."""

        model = models.AutomationGatewayModel
        fields = ["name", "description", "location", "location_descendants", "gateway", "enabled"]
