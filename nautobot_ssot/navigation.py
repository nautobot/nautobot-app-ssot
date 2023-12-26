"""App additions to the Nautobot navigation menu."""

from nautobot.apps.ui import NavMenuGroup, NavMenuItem, NavMenuTab


items = [
    NavMenuItem(
        link="plugins:nautobot_ssot:dashboard",
        name="Dashboard",
        permissions=["nautobot_ssot.view_sync"],
    ),
    NavMenuItem(
        link="plugins:nautobot_ssot:sync_list",
        name="History",
        permissions=["nautobot_ssot.view_sync"],
    ),
    NavMenuItem(
        link="plugins:nautobot_ssot:synclogentry_list",
        name="Logs",
        permissions=["nautobot_ssot.view_synclogentry"],
    ),
]

menu_items = (
    NavMenuTab(
        name="Plugins",
        groups=(NavMenuGroup(name="Single Source of Truth", weight=1000, items=tuple(items)),),
    ),
)
