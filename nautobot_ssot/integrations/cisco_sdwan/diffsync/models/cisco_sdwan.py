"""Cisco SD-WAN DiffSync models for the Cisco SD-WAN SSoT integration."""

from nautobot_ssot.integrations.cisco_sdwan.diffsync.models.base import (
    Device,
    DeviceType,
    Interface,
    IPAddressToInterface,
    SoftwareVersion,
)


class CiscoSdwanDevice(Device):
    """Cisco SD-WAN implementation of Device model."""


class CiscoSdwanDeviceType(DeviceType):
    """Cisco SD-WAN implementation of DeviceType model."""


class CiscoSdwanInterface(Interface):
    """Cisco SD-WAN implementation of Interface model."""


class CiscoSdwanIPAddressToInterface(IPAddressToInterface):
    """Cisco SD-WAN implementation of IPAddressToInterface model."""


class CiscoSdwanSoftwareVersion(SoftwareVersion):
    """Cisco SD-WAN implementation of SoftwareVersion model."""
