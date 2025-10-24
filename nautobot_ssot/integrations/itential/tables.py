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
    name = tables.Column(linkify=True)
    actions = ButtonsColumn(models.AutomationGatewayModel)

    class Meta(BaseTable.Meta):
        """Meta class definition."""

        model = models.AutomationGatewayModel
        fields = ["name", "description", "location", "location_descendants", "gateway", "enabled"]
        default_columns = (
            "name",
            "description",
            "location",
            "location_descendants",
            "gateway",
            "enabled",
            "actions",
        )
