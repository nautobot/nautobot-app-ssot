"""Nautobot DiffSync models for Panorama SSoT."""

from diffsync import exceptions as diffsync_exceptions
from nautobot.dcim.models.device_components import Interface as OrmInterface

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
from nautobot_ssot.integrations.panorama.utils.nautobot import Nautobot

NAUTOBOT = Nautobot()


class NautobotVdc(Vdc):
    """Nautobot implementation of Panorama Vdc model."""

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create Vdc in Nautobot from NautobotVdc object."""
        vdc = NAUTOBOT.create_vdc(adapter, ids, attrs)
        if not vdc:
            raise diffsync_exceptions.ObjectNotCreated
        return super().create(adapter=adapter, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update Vdc in Nautobot from NautobotVdc object."""
        vdc = NAUTOBOT.update_vdc(self.adapter, self.name, self.parent, attrs)
        if not vdc:
            raise diffsync_exceptions.ObjectNotUpdated
        return super().update(attrs)

    def delete(self):
        """Delete Vdc in Nautobot from NautobotVdc object."""
        return self


class NautobotVirtualDeviceContextAssociation(VirtualDeviceContextAssociation):
    """Nautobot implementation of VirtualDeviceContextAssociation model."""


class NautobotFirewall(Firewall):
    """Nautobot implementation of Panorama Firewall model."""

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create Firewall in Nautobot from NautobotFirewall object."""
        firewall = NAUTOBOT.create_firewall(adapter, ids, attrs)
        if not firewall:
            raise diffsync_exceptions.ObjectNotCreated
        return super().create(adapter=adapter, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update Firewall in Nautobot from NautobotFirewall object."""
        NAUTOBOT.update_firewall(self.adapter, self.serial, attrs)
        return super().update(attrs)

    def delete(self):
        """Delete Firewall in Nautobot from NautobotFirewall object."""
        return self


class NautobotFirewallInterface(FirewallInterface):
    """Nautobot implementation of IPAddressToInterface model."""

    def delete(self):
        """Delete Firewall Interface in Nautobot from NautobotFirewall object."""
        try:
            iface = OrmInterface.objects.get(name=self.name, device__serial=self.device__serial)
            super().delete()
            iface.delete()
        except Exception as e:
            raise diffsync_exceptions.ObjectNotDeleted(
                f"Failed to delete Interface: {self.name} in Firewall {self.device__serial}. Error {e}"
            )
        return self


class NautobotIPAddressToInterface(IPAddressToInterface):
    """Nautobot implementation of IPAddressToInterface model."""

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create IPAddressToInterface in Nautobot from NautobotIPAdderessToInterface object."""
        ip_address_to_interface = NAUTOBOT.create_ip_address_to_interface(adapter, ids)
        if not ip_address_to_interface:
            raise diffsync_exceptions.ObjectNotCreated
        return super().create(adapter=adapter, ids=ids, attrs=attrs)

    def delete(self):
        """Delete IPAddressToInterface in Nautobot from NautobotIPAdderessToInterface object."""
        NAUTOBOT.delete_ip_address_to_interface(adapter=self.adapter, ip_address_to_interface=self)
        return self


class NautobotSoftwareVersion(SoftwareVersion):
    """Nautobot implementation of SoftwareVersion model."""


class NautobotSoftwareVersionToDevice(SoftwareVersionToDevice):
    """Nautobot implementation of SoftwareVersionToDevice model."""

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Assign a software version to a device."""
        device = NAUTOBOT.create_software_version_to_device(adapter, ids, attrs)
        if not device:
            raise diffsync_exceptions.ObjectNotCreated
        return super().create(adapter=adapter, ids=ids, attrs=attrs)

    def delete(self):
        """Remove a software version from a device."""
        NAUTOBOT.delete_software_version_to_device(adapter=self.adapter, software_version_to_device=self)
        return self


class NautobotDeviceType(DeviceType):
    """Nautobot implementation of DeviceType model."""

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create DeviceType in Nautobot from NautobotDeviceType object."""
        device_type = NAUTOBOT.create_device_type(adapter, ids, attrs)
        if not device_type:
            raise diffsync_exceptions.ObjectNotCreated
        return super().create(adapter=adapter, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update DeviceType in Nautobot from NautobotDeviceType object."""
        identifiers = self.get_identifiers()
        device_type = NAUTOBOT.update_device_type(adapter=self.adapter, identifiers=identifiers, attrs=attrs)
        if not device_type:
            raise diffsync_exceptions.ObjectNotUpdated
        return super().update(attrs)


class NautobotControllerManagedDeviceGroup(ControllerManagedDeviceGroup):
    """Nautobot implementation of Panorama ControllerManagedDeviceGroup model."""


class NautobotDeviceToControllerManagedDeviceGroup(DeviceToControllerManagedDeviceGroup):
    """Nautobot implementation of Panorama DeviceToControllerManagedDeviceGroup model."""

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Add a device to a controller managed device group."""
        device = NAUTOBOT.create_device_to_controller_managed_device_group(adapter, ids, attrs)
        if not device:
            raise diffsync_exceptions.ObjectNotCreated
        return super().create(adapter=adapter, ids=ids, attrs=attrs)

    def delete(self):
        """Remove a device from a controller managed device group."""
        NAUTOBOT.delete_device_to_controller_managed_device_group(
            adapter=self.adapter, device_to_controller_managed_device_group=self
        )
        return self


class NautobotVdcToControllerManagedDeviceGroup(VdcToControllerManagedDeviceGroup):
    """Nautobot implementation of VdcToControllerManagedDeviceGroup."""
