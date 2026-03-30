"""Extensions of baseline Nautobot views."""

from django.urls import reverse
from nautobot.extras.plugins import TemplateExtension


class DeviceExtensions(TemplateExtension):  # pylint: disable=abstract-method
    """Add VirtualSystem & LogicalGroup to the tabs on the Device page."""

    model = "dcim.device"

    def detail_tabs(self):
        """Add tabs to the Devices detail view."""
        return [
            {
                "title": "Virtual Systems",
                "url": reverse(
                    "plugins:nautobot_ssot:virtualsystem_device_tab", kwargs={"pk": self.context["object"].pk}
                ),
            },
            {
                "title": "Logical Group",
                "url": reverse(
                    "plugins:nautobot_ssot:logicalgroup_device_tab", kwargs={"pk": self.context["object"].pk}
                ),
            },
        ]


template_extensions = [DeviceExtensions]
