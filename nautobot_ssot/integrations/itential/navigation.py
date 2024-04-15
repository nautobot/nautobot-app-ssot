"""Itential SSoT Navigation."""

from nautobot.apps.ui import NavMenuItem


nav_items = [
    NavMenuItem(
        link="plugins:nautobot_ssot:automationgatewaymodel_list",
        name="Itential Automation Gateway",
        permissions=["nautobot_ssot.view_sync"],
    ),
]
