"""Initialize models for Nautobot and Forward Enterprise."""
# pylint: disable=django-not-configured

from .base import (
    IPAddressModel,
    IPAssignmentModel,
    PrefixModel,
    VLANModel,
    VRFModel,
)
from .forward_enterprise import (
    DeviceModel,
    DeviceTypeModel,
    InterfaceModel,
    LocationModel,
    ManufacturerModel,
    PlatformModel,
    RoleModel,
)
from .nautobot import (
    NautobotIPAddressModel,
    NautobotIPAssignmentModel,
    NautobotPrefixModel,
    NautobotVLANModel,
    NautobotVRFModel,
)

__all__ = [
    # Base models (used by adapters)
    "IPAddressModel",
    "IPAssignmentModel",
    "PrefixModel",
    "VLANModel",
    "VRFModel",
    # Forward Enterprise models
    "DeviceModel",
    "DeviceTypeModel",
    "InterfaceModel",
    "LocationModel",
    "ManufacturerModel",
    "PlatformModel",
    "RoleModel",
    # Nautobot models
    "NautobotIPAddressModel",
    "NautobotIPAssignmentModel",
    "NautobotPrefixModel",
    "NautobotVLANModel",
    "NautobotVRFModel",
]
