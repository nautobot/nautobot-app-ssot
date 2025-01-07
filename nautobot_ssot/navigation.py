"""Menu items."""

from nautobot.apps.ui import NavMenuAddButton, NavMenuGroup, NavMenuItem, NavMenuTab

items = (
    NavMenuItem(
        link="plugins:nautobot_ssot:sync_list",
        name="Single Source of Truth",
        permissions=["nautobot_ssot.view_sync"],
        buttons=(
            NavMenuAddButton(
                link="plugins:nautobot_ssot:sync_add",
                permissions=["nautobot_ssot.add_sync"],
            ),
        ),
    ),
)

menu_items = (
    NavMenuTab(
        name="Apps",
        groups=(NavMenuGroup(name="Single Source of Truth", items=tuple(items)),),
    ),
)
