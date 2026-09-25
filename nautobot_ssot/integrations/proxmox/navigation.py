"""Proxmox VE SSoT Navigation."""

from nautobot.apps.ui import NavMenuItem

nav_items = [
    NavMenuItem(
        link="plugins:nautobot_ssot:ssotproxmoxconfig_list",
        name="Proxmox VE Config",
        weight=400,
        permissions=["nautobot_ssot.view_ssotproxmoxconfig"],
    ),
]
