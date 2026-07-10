"""Navigation for the Data Import integration."""

from nautobot.apps.ui import NavMenuItem

nav_items = [
    NavMenuItem(
        link="plugins:nautobot_ssot:importplan_list",
        name="Import Plans",
        permissions=["nautobot_ssot.view_importplan"],
    ),
]
