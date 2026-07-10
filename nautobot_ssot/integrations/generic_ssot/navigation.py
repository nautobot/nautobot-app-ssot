"""Generic SSoT Navigation."""

from nautobot.apps.ui import NavMenuItem

nav_items = [
    NavMenuItem(
        link="plugins:nautobot_ssot:ssotsyncconfig_list",
        name="Generic SSoT Configs",
        weight=500,
        permissions=["nautobot_ssot.view_ssotsyncconfig"],
    ),
    NavMenuItem(
        link="plugins:nautobot_ssot:ssotendpoint_list",
        name="SSoT Endpoints",
        weight=510,
        permissions=["nautobot_ssot.view_ssotendpoint"],
    ),
    NavMenuItem(
        link="plugins:nautobot_ssot:ssotfieldmapping_list",
        name="Field Mappings",
        weight=520,
        permissions=["nautobot_ssot.view_ssotfieldmapping"],
    ),
]
