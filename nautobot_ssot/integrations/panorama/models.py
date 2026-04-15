"""Models for the Panorama integration."""

from django.db import models
from nautobot.core.models import BaseModel


class VirtualDeviceContextToControllerManagedDeviceGroup(BaseModel):
    """Associates a VirtualDeviceContext with a ControllerManagedDeviceGroup."""

    controller_managed_device_group = models.ForeignKey(
        "dcim.ControllerManagedDeviceGroup",
        on_delete=models.CASCADE,
    )
    virtual_device_context = models.OneToOneField(
        "dcim.VirtualDeviceContext",
        on_delete=models.CASCADE,
    )
