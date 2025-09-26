"""App additions to the Nautobot navigation menu."""

from nautobot.apps.ui import (
    NavMenuAddButton,
    NavigationIconChoices,
    NavigationWeightChoices,
    NavMenuGroup,
    NavMenuItem,
    NavMenuTab,
)

from .integrations.utils import each_enabled_integration_module

items = [
    NavMenuItem(
        link="plugins:nautobot_ssot:dashboard",
        name="Dashboard",
        weight=100,
        permissions=["nautobot_ssot.view_sync"],
    ),
    NavMenuItem(
        link="plugins:nautobot_ssot:sync_list",
        name="History",
        weight=200,
        permissions=["nautobot_ssot.view_sync"],
    ),
    NavMenuItem(
        link="plugins:nautobot_ssot:synclogentry_list",
        name="Logs",
        weight=300,
        permissions=["nautobot_ssot.view_synclogentry"],
    ),
    NavMenuItem(
        link="plugins:nautobot_ssot:syncrecord_list",
        name="Sync Records",
        permissions=["nautobot_ssot.view_syncrecord"],
        buttons=(
            NavMenuAddButton(
                link="plugins:nautobot_ssot:syncrecord_add",
                permissions=["nautobot_ssot.add_syncrecord"],
            ),
        ),
    ),
]


def _add_integrations():
    for module in each_enabled_integration_module("navigation"):
        items.extend(module.nav_items)


_add_integrations()


menu_items = (
    NavMenuTab(
        name="Apps",
        icon=NavigationIconChoices.APPS,
        weight=NavigationWeightChoices.APPS,
        groups=(NavMenuGroup(name="Single Source of Truth", weight=400, items=tuple(items)),),
    ),
)
