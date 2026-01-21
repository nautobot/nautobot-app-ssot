"""Itential SSoT Navigation."""

from nautobot.apps.ui import NavMenuItem

nav_items = [
    NavMenuItem(
        link="plugins:nautobot_ssot:automationgatewaymodel_list",
        name="Itential Automation Gateway",
        weight=400,
        permissions=["nautobot_ssot.view_sync"],
    ),
]
