"""Adds plugin items to homepage."""

from nautobot.core.apps import HomePageItem, HomePagePanel

from nautobot_ssot.integrations.panorama.models import LogicalGroup, VirtualSystem

layout = (
    HomePagePanel(
        weight=150,
        name="Devices",
        items=(
            HomePageItem(
                name="Virtual Systems",
                model=VirtualSystem,
                weight=100,
                link="plugins:nautobot_ssot:virtualsystem_list",
                description="Firewall Virtual Systems",
                permissions=["nautobot_ssot.view_virtualsystem"],
            ),
            HomePageItem(
                name="Logical Groups",
                model=LogicalGroup,
                weight=100,
                link="plugins:nautobot_ssot:logicalgroup_list",
                description="Firewall Logical Groups",
                permissions=["nautobot_ssot.view_logicalgroup"],
            ),
        ),
    ),
)
