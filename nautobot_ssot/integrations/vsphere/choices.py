"""Choicesets for vSphere integration."""

from nautobot.apps.choices import ChoiceSet


class PrimaryIpSortByChoices(ChoiceSet):
    """Choiceset used by SSOTvSphereConfig."""

    LOWEST = "Lowest"
    HIGHEST = "Highest"

    CHOICES = (
        (LOWEST, "Lowest"),
        (HIGHEST, "Highest"),
    )
