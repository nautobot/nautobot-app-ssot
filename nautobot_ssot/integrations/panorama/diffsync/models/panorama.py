"""Nautobot SSoT Panorama DiffSync models for Nautobot SSoT Panorama SSoT."""

from nautobot_ssot.integrations.panorama.diffsync.models.base import (
    ControllerManagedDeviceGroup,
    DeviceToControllerManagedDeviceGroup,
    DeviceType,
    Firewall,
    FirewallInterface,
    IPAddressToInterface,
    LogicalGroup,
    LogicalGroupToDevice,
    LogicalGroupToVirtualDeviceContext,
    LogicalGroupToVirtualSystem,
    SoftwareVersion,
    SoftwareVersionToDevice,
    Vdc,
    VirtualDeviceContextAssociation,
    VirtualSystemAssociation,
    Vsys,
)


class PanoramaVsys(Vsys):
    """Panorama implementation of Vsys model."""


class PanoramaVdc(Vdc):
    """Panorama implementation of Vsys model."""


class PanoramaVirtualSystemAssociation(VirtualSystemAssociation):
    """Panorama implementation of VirtualSystemAssociation model."""


class PanoramaVirtualDeviceContextAssociation(VirtualDeviceContextAssociation):
    """Panorama implementation of VirtualDeviceContextAssociation model."""


class PanoramaLogicalGroupToVirtualSystem(LogicalGroupToVirtualSystem):
    """Panorama implementation of LogicalGroupToVirtualSystem model."""


class PanoramaLogicalGroupToVirtualDeviceContext(LogicalGroupToVirtualDeviceContext):
    """Panorama implementation of LogicalGroupToVirtualDeviceContext model."""


class PanoramaLogicalGroupToDevice(LogicalGroupToDevice):
    """Panorama implementation of LogicalGroupToDevice model."""


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


class PanoramaLogicalGroup(LogicalGroup):
    """Panorama implementation of LogicalGroup model."""
