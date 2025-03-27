# pylint: disable=duplicate-code
"""Nautobot Adapter for SolarWinds SSoT app."""

from nautobot_ssot.contrib.adapter import NautobotAdapter as BaseNautobotAdapter
from nautobot_ssot.integrations.solarwinds.diffsync.models.base import (
    DeviceModel,
    DeviceTypeModel,
    InterfaceModel,
    IPAddressModel,
    LocationModel,
    ManufacturerModel,
    PlatformModel,
    PrefixModel,
    RoleModel,
    SoftwareVersionModel,
)
from nautobot_ssot.integrations.solarwinds.diffsync.models.nautobot import (
    NautobotIPAddressToInterfaceModel,
)


class NautobotAdapter(BaseNautobotAdapter):
    """DiffSync adapter for Nautobot."""

    location = LocationModel
    platform = PlatformModel
    role = RoleModel
    manufacturer = ManufacturerModel
    device_type = DeviceTypeModel
    softwareversion = SoftwareVersionModel
    device = DeviceModel
    interface = InterfaceModel
    prefix = PrefixModel
    ipaddress = IPAddressModel
    ipassignment = NautobotIPAddressToInterfaceModel

    top_level = [
        "location",
        "manufacturer",
        "platform",
        "role",
        "softwareversion",
        "device",
        "prefix",
        "ipaddress",
        "ipassignment",
    ]

    def load_param_mac_address(self, parameter_name, database_object):
        """Custom loader for 'mac_address' parameter."""
        mac_addr = getattr(database_object, parameter_name)
        if mac_addr is not None:
            return str(mac_addr)
        return mac_addr
