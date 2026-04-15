"""Nautobot SSoT Panorama DiffSync models for Nautobot SSoT Panorama SSoT."""

from nautobot_ssot.integrations.panorama.diffsync.models.base import (
    ControllerManagedDeviceGroup,
    DeviceToControllerManagedDeviceGroup,
    DeviceType,
    Firewall,
    FirewallInterface,
    IPAddressToInterface,
    SoftwareVersion,
    SoftwareVersionToDevice,
    Vdc,
    VdcToControllerManagedDeviceGroup,
    VirtualDeviceContextAssociation,
)


class PanoramaVdc(Vdc):
    """Panorama implementation of Vdc model."""


class PanoramaVirtualDeviceContextAssociation(VirtualDeviceContextAssociation):
    """Panorama implementation of VirtualDeviceContextAssociation model."""


class PanoramaFirewall(Firewall):
    """Panorama implementation of Firewall model."""


class PanoramaFirewallInterface(FirewallInterface):
    """Panorama implementation of FirewallInterface model."""


class PanoramaIPAddressToInterface(IPAddressToInterface):
    """Panorama implementation of IPAddressToInterface model."""


class PanoramaSoftwareVersion(SoftwareVersion):
    """Panorama implementation of SoftwareVersion model."""


class PanoramaSoftwareVersionToDevice(SoftwareVersionToDevice):
    """Panorama implementation of SoftwareVersionToDevice model."""


class PanoramaDeviceType(DeviceType):
    """Panorama implementation of DeviceType model."""


class PanoramaControllerManagedDeviceGroup(ControllerManagedDeviceGroup):
    """Panorama implementation of ControllerManagedDeviceGroup model."""


class PanoramaDeviceToControllerManagedDeviceGroup(DeviceToControllerManagedDeviceGroup):
    """Panorama implementation of DeviceToControllerManagedDeviceGroup model."""


class PanoramaVdcToControllerManagedDeviceGroup(VdcToControllerManagedDeviceGroup):
    """Panorama implementation of VdcToControllerManagedDeviceGroup model."""
