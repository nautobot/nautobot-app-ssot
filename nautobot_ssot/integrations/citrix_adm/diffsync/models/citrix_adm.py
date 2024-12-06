"""Nautobot SSoT Citrix ADM DiffSync models for Nautobot SSoT Citrix ADM SSoT."""

from nautobot_ssot.integrations.citrix_adm.diffsync.models.base import (
    Address,
    Datacenter,
    Device,
    IPAddressOnInterface,
    OSVersion,
    Port,
    Subnet,
)


class CitrixAdmDatacenter(Datacenter):
    """Citrix ADM implementation of Datacenter DiffSync model."""

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create Site in Citrix ADM from Datacenter object."""
        raise NotImplementedError

    def update(self, attrs):
        """Update Site in Citrix ADM from Datacenter object."""
        raise NotImplementedError

    def delete(self):
        """Delete Site in Citrix ADM from Datacenter object."""
        raise NotImplementedError


class CitrixAdmOSVersion(OSVersion):
    """Citrix ADM implementation of OSVersion DiffSync model."""

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create OSVersion in Citrix ADM from OSVersion object."""
        raise NotImplementedError

    def update(self, attrs):
        """Update OSVersion in Citrix ADM from OSVersion object."""
        raise NotImplementedError

    def delete(self):
        """Delete OSVersion in Citrix ADM from OSVersion object."""
        raise NotImplementedError


class CitrixAdmDevice(Device):
    """Citrix ADM implementation of Device DiffSync model."""

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create Device in Citrix ADM from Device object."""
        raise NotImplementedError

    def update(self, attrs):
        """Update Device in Citrix ADM from Device object."""
        raise NotImplementedError

    def delete(self):
        """Delete Device in Citrix ADM from Device object."""
        raise NotImplementedError


class CitrixAdmPort(Port):
    """Citrix ADM implementation of Port DiffSync model."""

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create Interface in Citrix ADM from Port object."""
        raise NotImplementedError

    def update(self, attrs):
        """Update Interface in Citrix ADM from Port object."""
        raise NotImplementedError

    def delete(self):
        """Delete Interface in Citrix ADM from Port object."""
        raise NotImplementedError


class CitrixAdmSubnet(Subnet):
    """Citrix ADM implementation of Subnet DiffSync model."""

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create Prefix in Citrix ADM from Subnet object."""
        raise NotImplementedError

    def update(self, attrs):
        """Update Prefix in Citrix ADM from Subnet object."""
        raise NotImplementedError

    def delete(self):
        """Delete Prefix in Citrix ADM from Subnet object."""
        raise NotImplementedError


class CitrixAdmAddress(Address):
    """Citrix ADM implementation of Address DiffSync model."""

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create IP Address in Citrix ADM from Address object."""
        raise NotImplementedError

    def update(self, attrs):
        """Update IP Address in Citrix ADM from Address object."""
        raise NotImplementedError

    def delete(self):
        """Delete IP Address in Citrix ADM from Address object."""
        raise NotImplementedError


class CitrixAdmIPAddressOnInterface(IPAddressOnInterface):
    """Citrix ADM implementation of IPAddressOnInterface DiffSync model."""

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create IPAddressToInterface in Citrix ADM from CitrixAdmIPAddressOnInterface object."""
        raise NotImplementedError

    def update(self, attrs):
        """Update IPAddressToInterface in Citrix ADM from CitrixAdmIPAddressOnInterface object."""
        raise NotImplementedError

    def delete(self):
        """Delete IPAddressToInterface in Citrix ADM from CitrixAdmIPAddressOnInterface object."""
        raise NotImplementedError
