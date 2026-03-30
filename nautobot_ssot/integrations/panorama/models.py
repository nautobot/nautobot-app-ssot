"""Models extending the Firewall plugin."""

from django.db import models
from django.urls import reverse
from nautobot.apps.models import TreeManager
from nautobot.core.models import BaseModel
from nautobot.core.models.generics import PrimaryModel
from nautobot.extras.utils import extras_features
from tree_queries.models import TreeNode


@extras_features(
    "custom_fields",
    "custom_links",
    "custom_validators",
    "export_templates",
    "graphql",
    "relationships",
    "statuses",
    "webhooks",
)
class VirtualSystem(PrimaryModel):  # pylint: disable=too-many-ancestors
    """Models Palo Alto VSYS."""

    system_id = models.PositiveSmallIntegerField()
    name = models.CharField(max_length=48)
    device = models.ForeignKey(to="dcim.Device", related_name="vsys", on_delete=models.CASCADE)
    interfaces = models.ManyToManyField(
        to="dcim.Interface", related_name="assigned_vsys", through="VirtualSystemAssociation"
    )

    class Meta:
        """Meta class."""

        ordering = ["name"]
        verbose_name = "Virtual System"
        verbose_name_plural = "Virtual Systems"
        unique_together = [["device", "name"]]

    def get_absolute_url(self, api=False):
        """Return detail view URL."""
        return reverse("plugins:nautobot_ssot:virtualsystem", args=[self.pk])

    def __str__(self):
        """Stringify instance."""
        return self.name


class VirtualSystemAssociation(BaseModel):
    """Enforce an interface is not assigned more than once."""

    vsys = models.ForeignKey("nautobot_ssot.VirtualSystem", on_delete=models.CASCADE)
    iface = models.OneToOneField("dcim.Interface", on_delete=models.CASCADE)


@extras_features(
    "custom_fields",
    "custom_links",
    "custom_validators",
    "export_templates",
    "graphql",
    "relationships",
    "statuses",
    "webhooks",
)
class LogicalGroup(TreeNode, PrimaryModel):  # pylint: disable=too-many-ancestors
    """Logical grouping of Devices & VirtualSystems."""

    name = models.CharField(max_length=48, unique=True)
    devices = models.ManyToManyField(to="dcim.Device", related_name="logical_group", through="LogicalGroupToDevice")
    virtual_systems = models.ManyToManyField(
        to="nautobot_ssot.VirtualSystem", related_name="logical_group", through="LogicalGroupToVirtualSystem"
    )
    control_plane = models.ForeignKey(
        to="dcim.Controller",
        null=True,
        blank=True,
        related_name="logical_groups",
        on_delete=models.CASCADE,
    )

    objects = TreeManager()

    class Meta:
        """Meta class."""

        ordering = ["name"]
        verbose_name = "Logical Group"
        verbose_name_plural = "Logical Groups"

    def get_absolute_url(self, api=False):
        """Return detail view URL."""
        return reverse("plugins:nautobot_ssot:logicalgroup", args=[self.pk])

    def __str__(self):
        """Stringify instance."""
        return self.name


class LogicalGroupToDevice(BaseModel):
    """Enforce a Device is not assigned more than once."""

    group = models.ForeignKey("nautobot_ssot.LogicalGroup", on_delete=models.CASCADE)
    device = models.OneToOneField("dcim.Device", on_delete=models.CASCADE)


class LogicalGroupToVirtualSystem(BaseModel):
    """Enforce a VirtualSystem is not assigned more than once."""

    group = models.ForeignKey("nautobot_ssot.LogicalGroup", on_delete=models.CASCADE)
    vsys = models.OneToOneField("nautobot_ssot.VirtualSystem", on_delete=models.CASCADE)
