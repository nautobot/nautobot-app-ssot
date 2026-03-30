"""Menu items."""

from nautobot.core.apps import NavMenuAddButton, NavMenuGroup, NavMenuItem, NavMenuTab

nav_items = [
    NavMenuItem(
        link="plugins:nautobot_ssot:virtualsystem_list",
        name="Virtual Systems",
        permissions=["nautobot_ssot.view_virtualsystem"],
        buttons=[
            NavMenuAddButton(
                link="plugins:nautobot_ssot:virtualsystem_add",
                permissions=["nautobot_ssot.add_virtualsystem"],
            ),
        ],
    ),
    NavMenuItem(
        link="plugins:nautobot_ssot:logicalgroup_list",
        name="Logical Groups",
        permissions=["nautobot_ssot.view_logicalgroup"],
        buttons=[
            NavMenuAddButton(
                link="plugins:nautobot_ssot:logicalgroup_add",
                permissions=["nautobot_ssot.add_logicalgroup"],
            ),
        ],
    ),
]
