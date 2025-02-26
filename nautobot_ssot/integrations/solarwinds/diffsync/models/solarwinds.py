"""Nautobot SSoT SolarWinds DiffSync models for Nautobot SSoT SolarWinds SSoT."""

from nautobot_ssot.integrations.solarwinds.diffsync.models.base import (
    DeviceModel,
    DeviceTypeModel,
    InterfaceModel,
    IPAddressModel,
    IPAddressToInterfaceModel,
    LocationModel,
    ManufacturerModel,
    PlatformModel,
    PrefixModel,
    RoleModel,
    SoftwareVersionModel,
)


class SolarWindsLocation(LocationModel):
    """SolarWinds implementation of Location DiffSync model."""

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create Location in SolarWinds from SolarWindsLocation object."""
        raise NotImplementedError

    def update(self, attrs):
        """Update Location in SolarWinds from SolarWindsLocation object."""
        raise NotImplementedError

    def delete(self):
        """Delete Location in SolarWinds from SolarWindsLocation object."""
        raise NotImplementedError


class SolarWindsDeviceType(DeviceTypeModel):
    """SolarWinds implementation of DeviceType DiffSync model."""

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create DeviceType in SolarWinds from SolarWindsDeviceType object."""
        raise NotImplementedError

    def update(self, attrs):
        """Update DeviceType in SolarWinds from SolarWindsDeviceType object."""
        raise NotImplementedError

    def delete(self):
        """Delete DeviceType in SolarWinds from SolarWindsDeviceType object."""
        raise NotImplementedError


class SolarWindsManufacturer(ManufacturerModel):
    """SolarWinds implementation of Manufacturer DiffSync model."""

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create Manufacturer in SolarWinds from SolarWindsManufacturer object."""
        raise NotImplementedError

    def update(self, attrs):
        """Update Manufacturer in SolarWinds from SolarWindsManufacturer object."""
        raise NotImplementedError

    def delete(self):
        """Delete Manufacturer in SolarWinds from SolarWindsManufacturer object."""
        raise NotImplementedError


class SolarWindsPlatform(PlatformModel):
    """SolarWinds implementation of Platform DiffSync model."""

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create Platform in SolarWinds from SolarWindsPlatform object."""
        raise NotImplementedError

    def update(self, attrs):
        """Update Platform in SolarWinds from SolarWindsPlatform object."""
        raise NotImplementedError

    def delete(self):
        """Delete Platform in SolarWinds from SolarWindsPlatform object."""
        raise NotImplementedError


class SolarWindsSoftwareVersion(SoftwareVersionModel):
    """SolarWinds implementation of SoftwareVersion DiffSync model."""

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create SoftwareVersion in SolarWinds from SolarWindsSoftwareVersion object."""
        raise NotImplementedError

    def update(self, attrs):
        """Update SoftwareVersion in SolarWinds from SolarWindsSoftwareVersion object."""
        raise NotImplementedError

    def delete(self):
        """Delete SoftwareVersion in SolarWinds from SolarWindsSoftwareVersion object."""
        raise NotImplementedError


class SolarWindsRole(RoleModel):
    """SolarWinds implementation of Role DiffSync model."""

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create Role in SolarWinds from SolarWindsRole object."""
        raise NotImplementedError

    def update(self, attrs):
        """Update Role in SolarWinds from SolarWindsRole object."""
        raise NotImplementedError

    def delete(self):
        """Delete Role in SolarWinds from SolarWindsRole object."""
        raise NotImplementedError


class SolarWindsDevice(DeviceModel):
    """SolarWinds implementation of Device DiffSync model."""

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create Device in SolarWinds from SolarWindsDevice object."""
        raise NotImplementedError

    def update(self, attrs):
        """Update Device in SolarWinds from SolarWindsDevice object."""
        raise NotImplementedError

    def delete(self):
        """Delete Device in SolarWinds from SolarWindsDevice object."""
        raise NotImplementedError


class SolarWindsInterface(InterfaceModel):
    """SolarWinds implementation of Interface DiffSync model."""

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create Interface in SolarWinds from SolarWindsInterface object."""
        raise NotImplementedError

    def update(self, attrs):
        """Update Interface in SolarWinds from SolarWindsInterface object."""
        raise NotImplementedError

    def delete(self):
        """Delete Interface in SolarWinds from SolarWindsInterface object."""
        raise NotImplementedError


class SolarWindsPrefix(PrefixModel):
    """SolarWinds implementation of Prefix DiffSync model."""

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create Prefix in SolarWinds from SolarWindsPrefix object."""
        raise NotImplementedError

    def update(self, attrs):
        """Update Prefix in SolarWinds from SolarWindsPrefix object."""
        raise NotImplementedError

    def delete(self):
        """Delete Prefix in SolarWinds from SolarWindsPrefix object."""
        raise NotImplementedError


class SolarWindsIPAddress(IPAddressModel):
    """SolarWinds implementation of IPAddress DiffSync model."""

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create IPAddress in SolarWinds from SolarWindsIPAddress object."""
        raise NotImplementedError

    def update(self, attrs):
        """Update IPAddress in SolarWinds from SolarWindsIPAddress object."""
        raise NotImplementedError

    def delete(self):
        """Delete IPAddress in SolarWinds from SolarWindsIPAddress object."""
        raise NotImplementedError


class SolarWindsIPAddressToInterface(IPAddressToInterfaceModel):
    """SolarWinds implementation of IPAddressToInterface DiffSync model."""

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create IPAddressToInterface in SolarWinds from SolarWindsIPAddressToInterface object."""
        raise NotImplementedError

    def update(self, attrs):
        """Update IPAddressToInterface in SolarWinds from SolarWindsIPAddressToInterface object."""
        raise NotImplementedError

    def delete(self):
        """Delete IPAddressToInterface in SolarWinds from SolarWindsIPAddressToInterface object."""
        raise NotImplementedError
