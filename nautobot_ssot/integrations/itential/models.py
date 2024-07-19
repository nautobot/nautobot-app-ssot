"""Models for Nautobot Itential."""

# Django imports
from django.db import models

# Nautobot imports
from nautobot.apps.models import PrimaryModel
from nautobot.dcim.models import Location
from nautobot.extras.models import ExternalIntegration


class AutomationGatewayModel(PrimaryModel):  # pylint: disable=too-many-ancestors
    """Automation Gateway model for Nautobot Itential app."""

    name = models.CharField(max_length=255, unique=True)
    description = models.CharField(max_length=512, blank=True)
    location = models.ForeignKey(
        Location,
        on_delete=models.CASCADE,
        verbose_name="Location",
        help_text="Automation Gateway manages devices from this location.",
    )
    location_descendants = models.BooleanField(
        default=True,
        verbose_name="Include Location Descendants",
        help_text="Include descendant locations.",
    )
    gateway = models.OneToOneField(
        ExternalIntegration,
        on_delete=models.CASCADE,
        verbose_name="Automation Gateway",
        help_text="Automation Gateway server defined from external integration model.",
    )
    enabled = models.BooleanField(
        default=False,
        verbose_name="Automation Gateway enabled",
        help_text="Enable or Disable the Automation Gateway from being managed by Nautobot.",
    )

    class Meta:
        """Meta class."""

        ordering = ["name", "location"]
        verbose_name = "Automation Gateway Management"
        verbose_name_plural = "Automation Gateway Management"

    def __str__(self):
        """Stringify instance."""
        return self.name
