# pylint: disable=useless-parent-delegation
"""Nautobot SSoT for Meraki DiffSync models for Nautobot SSoT for Meraki SSoT."""

from nautobot_ssot.integrations.meraki.diffsync.models.base import (
    Device,
    Hardware,
    IPAddress,
    IPAssignment,
    Network,
    OSVersion,
    Port,
    Prefix,
    PrefixLocation,
)


class MerakiNetwork(Network):
    """Meraki implementation of Network DiffSync model."""

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create Network in Meraki from MerakiNetwork object."""
        return super().create(adapter=adapter, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update Network in Meraki from MerakiNetwork object."""
        return super().update(attrs)

    def delete(self):
        """Delete Network in Meraki from MerakiNetwork object."""
        return self


class MerakiHardware(Hardware):
    """Meraki implementation of Hardware DiffSync model."""

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create Hardware in Meraki from MerakiHardware object."""
        return super().create(adapter=adapter, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update Hardware in Meraki from MerakiHardware object."""
        return super().update(attrs)

    def delete(self):
        """Delete Hardware in Meraki from MerakiHardware object."""
        return self


class MerakiOSVersion(OSVersion):
    """Meraki implementation of OSVersion DiffSync model."""

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create OSVersion in Meraki from MerakiOSVersion object."""
        return super().create(adapter=adapter, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update OSVersion in Meraki from MerakiOSVersion object."""
        return super().update(attrs)

    def delete(self):
        """Delete OSVersion in Meraki from MerakiOSVersion object."""
        return self


class MerakiDevice(Device):
    """Meraki implementation of Device DiffSync model."""

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create Device in Meraki from MerakiDevice object."""
        return super().create(adapter=adapter, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update Device in Meraki from MerakiDevice object."""
        return super().update(attrs)

    def delete(self):
        """Delete Device in Meraki from MerakiDevice object."""
        return self


class MerakiPort(Port):
    """Meraki implementation of Port DiffSync model."""

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create Port in Meraki from MerakiPort object."""
        return super().create(adapter=adapter, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update Port in Meraki from MerakiPort object."""
        return super().update(attrs)

    def delete(self):
        """Delete Port in Meraki from MerakiPort object."""
        return self


class MerakiPrefix(Prefix):
    """Meraki implementation of Prefix DiffSync model."""

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create Prefix in Meraki from MerakiPrefix object."""
        return super().create(adapter=adapter, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update Prefix in Meraki from MerakiPrefix object."""
        return super().update(attrs)

    def delete(self):
        """Delete Prefix in Meraki from MerakiPrefix object."""
        return self


class MerakiPrefixLocation(PrefixLocation):
    """Meraki implementation of PrefixLocation DiffSync model."""

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create PrefixLocation in Meraki from MerakiPrefixLocation object."""
        return super().create(adapter=adapter, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update PrefixLocation in Meraki from MerakiPrefixLocation object."""
        return super().update(attrs)

    def delete(self):
        """Delete PrefixLocation in Meraki from MerakiPrefixLocation object."""
        return self


class MerakiIPAddress(IPAddress):
    """Meraki implementation of IPAddress DiffSync model."""

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create IPAddress in Meraki from MerakiIPAddress object."""
        return super().create(adapter=adapter, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update IPAddress in Meraki from MerakiIPAddress object."""
        return super().update(attrs)

    def delete(self):
        """Delete IPAddress in Meraki from MerakiIPAddress object."""
        return self


class MerakiIPAssignment(IPAssignment):
    """Meraki implementation of IPAddress DiffSync model."""

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create IPAddressToInterface in Meraki from MerakiIPAssignment object."""
        return super().create(adapter=adapter, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update IPAddressToInterface in Meraki from MerakiIPAssignment object."""
        return super().update(attrs)

    def delete(self):
        """Delete IPAddressToInterface in Meraki from MerakiIPAssignment object."""
        return self
