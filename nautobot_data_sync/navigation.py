"""Plugin additions to the Nautobot navigation menu."""

from nautobot.extras.plugins import PluginMenuItem, PluginMenuButton
from nautobot.utilities.choices import ButtonColorChoices


menu_items = (
    PluginMenuItem(
        link="plugins:nautobot_data_sync:sync_list",
        link_text="Data Syncs",
        permissions=["nautobot_data_sync.view_sync"],
    ),
    PluginMenuItem(
        link="plugins:nautobot_data_sync:synclogentry_list",
        link_text="Data Sync Detailed Logs",
        permissions=["nautobot_data_sync.view_synclogentry"],
    ),
)
