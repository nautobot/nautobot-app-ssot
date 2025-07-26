"""OpenShift SSoT Navigation."""

from nautobot.apps.ui import NavMenuItem

nav_items = [
    NavMenuItem(
        link="plugins:nautobot_ssot:openshift:config_list",
        name="OpenShift Configurations",
        permissions=["nautobot_ssot.view_ssotopenshiftconfig"],
    ),
] 