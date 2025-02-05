"""Diffsync models for nautobot_ssot_uisp."""
from typing import Optional, Annotated


from nautobot.dcim.models import Device

from nautobot_ssot.contrib import CustomFieldAnnotation, NautobotModel


class DeviceSSoTModel(NautobotModel):
    """SSoT model for UISP devices."""

    _model = Device
    _modelname = "device"
    _identifiers = ("name",)
    _attributes = (
        "status__name",
        "role__name",
        "device_type__name",
        "location__name",
        "example_custom_field"
    )

    name: str
    status__name: Optional[str] = None
    role__name: Optional[str] = None
    device_type__name: Optional[str] = None
    location__name: Optional[str] = None
    ip_address: Optional[str] = None
    example_custom_field: Annotated[str, CustomFieldAnnotation(key="my_example_custom_field")]
    