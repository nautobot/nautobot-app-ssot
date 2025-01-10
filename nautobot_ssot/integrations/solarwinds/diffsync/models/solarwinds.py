"""Nautobot SSoT Solarwinds DiffSync models for Nautobot SSoT Solarwinds SSoT."""

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


class SolarwindsLocation(LocationModel):
    """Solarwinds implementation of Location DiffSync model."""

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create Location in Solarwinds from SolarwindsLocation object."""
        raise NotImplementedError

    def update(self, attrs):
        """Update Location in Solarwinds from SolarwindsLocation object."""
        raise NotImplementedError

    def delete(self):
        """Delete Location in Solarwinds from SolarwindsLocation object."""
        raise NotImplementedError


class SolarwindsDeviceType(DeviceTypeModel):
    """Solarwinds implementation of DeviceType DiffSync model."""

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create DeviceType in Solarwinds from SolarwindsDeviceType object."""
        raise NotImplementedError

    def update(self, attrs):
        """Update DeviceType in Solarwinds from SolarwindsDeviceType object."""
        raise NotImplementedError

    def delete(self):
        """Delete DeviceType in Solarwinds from SolarwindsDeviceType object."""
        raise NotImplementedError


class SolarwindsManufacturer(ManufacturerModel):
    """Solarwinds implementation of Manufacturer DiffSync model."""

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create Manufacturer in Solarwinds from SolarwindsManufacturer object."""
        raise NotImplementedError

    def update(self, attrs):
        """Update Manufacturer in Solarwinds from SolarwindsManufacturer object."""
        raise NotImplementedError

    def delete(self):
        """Delete Manufacturer in Solarwinds from SolarwindsManufacturer object."""
        raise NotImplementedError


class SolarwindsPlatform(PlatformModel):
    """Solarwinds implementation of Platform DiffSync model."""

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create Platform in Solarwinds from SolarwindsPlatform object."""
        raise NotImplementedError

    def update(self, attrs):
        """Update Platform in Solarwinds from SolarwindsPlatform object."""
        raise NotImplementedError

    def delete(self):
        """Delete Platform in Solarwinds from SolarwindsPlatform object."""
        raise NotImplementedError


class SolarwindsSoftwareVersion(SoftwareVersionModel):
    """Solarwinds implementation of SoftwareVersion DiffSync model."""

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create SoftwareVersion in Solarwinds from SolarwindsSoftwareVersion object."""
        raise NotImplementedError

    def update(self, attrs):
        """Update SoftwareVersion in Solarwinds from SolarwindsSoftwareVersion object."""
        raise NotImplementedError

    def delete(self):
        """Delete SoftwareVersion in Solarwinds from SolarwindsSoftwareVersion object."""
        raise NotImplementedError


class SolarwindsRole(RoleModel):
    """Solarwinds implementation of Role DiffSync model."""

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create Role in Solarwinds from SolarwindsRole object."""
        raise NotImplementedError

    def update(self, attrs):
        """Update Role in Solarwinds from SolarwindsRole object."""
        raise NotImplementedError

    def delete(self):
        """Delete Role in Solarwinds from SolarwindsRole object."""
        raise NotImplementedError


class SolarwindsDevice(DeviceModel):
    """Solarwinds implementation of Device DiffSync model."""

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create Device in Solarwinds from SolarwindsDevice object."""
        raise NotImplementedError

    def update(self, attrs):
        """Update Device in Solarwinds from SolarwindsDevice object."""
        raise NotImplementedError

    def delete(self):
        """Delete Device in Solarwinds from SolarwindsDevice object."""
        raise NotImplementedError


class SolarwindsInterface(InterfaceModel):
    """Solarwinds implementation of Interface DiffSync model."""

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create Interface in Solarwinds from SolarwindsInterface object."""
        raise NotImplementedError

    def update(self, attrs):
        """Update Interface in Solarwinds from SolarwindsInterface object."""
        raise NotImplementedError

    def delete(self):
        """Delete Interface in Solarwinds from SolarwindsInterface object."""
        raise NotImplementedError


class SolarwindsPrefix(PrefixModel):
    """Solarwinds implementation of Prefix DiffSync model."""

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create Prefix in Solarwinds from SolarwindsPrefix object."""
        raise NotImplementedError

    def update(self, attrs):
        """Update Prefix in Solarwinds from SolarwindsPrefix object."""
        raise NotImplementedError

    def delete(self):
        """Delete Prefix in Solarwinds from SolarwindsPrefix object."""
        raise NotImplementedError


class SolarwindsIPAddress(IPAddressModel):
    """Solarwinds implementation of IPAddress DiffSync model."""

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create IPAddress in Solarwinds from SolarwindsIPAddress object."""
        raise NotImplementedError

    def update(self, attrs):
        """Update IPAddress in Solarwinds from SolarwindsIPAddress object."""
        raise NotImplementedError

    def delete(self):
        """Delete IPAddress in Solarwinds from SolarwindsIPAddress object."""
        raise NotImplementedError


class SolarwindsIPAddressToInterface(IPAddressToInterfaceModel):
    """Solarwinds implementation of IPAddressToInterface DiffSync model."""

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create IPAddressToInterface in Solarwinds from SolarwindsIPAddressToInterface object."""
        raise NotImplementedError

    def update(self, attrs):
        """Update IPAddressToInterface in Solarwinds from SolarwindsIPAddressToInterface object."""
        raise NotImplementedError

    def delete(self):
        """Delete IPAddressToInterface in Solarwinds from SolarwindsIPAddressToInterface object."""
        raise NotImplementedError
