"""Choicesets for Proxmox VE integration."""

from nautobot.apps.choices import ChoiceSet


class PrimaryIpSortByChoices(ChoiceSet):
    """Choiceset used by SSOTProxmoxConfig to pick a Virtual Machine's primary IP."""

    LOWEST = "Lowest"
    HIGHEST = "Highest"

    CHOICES = (
        (LOWEST, "Lowest"),
        (HIGHEST, "Highest"),
    )
