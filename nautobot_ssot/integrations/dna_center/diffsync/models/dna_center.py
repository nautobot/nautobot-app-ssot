"""Nautobot SSoT for Cisco DNA Center DiffSync models for Nautobot SSoT for Cisco DNA Center SSoT."""

from nautobot_ssot.integrations.dna_center.diffsync.models.base import (
    Area,
    Building,
    Device,
    Floor,
    IPAddress,
    IPAddressOnInterface,
    Port,
    Prefix,
)


class DnaCenterArea(Area):
    """DNA Center implementation of Building DiffSync model."""

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create Area in DNA Center from Area object."""
        return super().create(adapter=adapter, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update Area in DNA Center from Area object."""
        return super().update(attrs)

    def delete(self):
        """Delete Area in DNA Center from Area object."""
        return self


class DnaCenterBuilding(Building):
    """DNA Center implementation of Building DiffSync model."""

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create Building in DNA Center from Building object."""
        return super().create(adapter=adapter, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update Building in DNA Center from Building object."""
        return super().update(attrs)

    def delete(self):
        """Delete Building in DNA Center from Building object."""
        return self


class DnaCenterFloor(Floor):
    """DNA Center implementation of Floor DiffSync model."""

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create Floor in DNA Center from Floor object."""
        return super().create(adapter=adapter, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update Floor in DNA Center from Floor object."""
        return super().update(attrs)

    def delete(self):
        """Delete Floor in DNA Center from Floor object."""
        return self


class DnaCenterDevice(Device):
    """DNA Center implementation of Device DiffSync model."""

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create Device in DNA Center from Device object."""
        return super().create(adapter=adapter, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update Device in DNA Center from Device object."""
        return super().update(attrs)

    def delete(self):
        """Delete Device in DNA Center from Device object."""
        return self


class DnaCenterPort(Port):
    """DNA Center implementation of Port DiffSync model."""

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create Interface in DNA Center from Port object."""
        return super().create(adapter=adapter, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update Interface in DNA Center from Port object."""
        return super().update(attrs)

    def delete(self):
        """Delete Interface in DNA Center from Port object."""
        return self


class DnaCenterPrefix(Prefix):
    """DNA Center implementation of Prefix Diffsync model."""

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create Prefix in Dna Center from Prefix Diffsync model."""
        return super().create(adapter=adapter, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update Prefix in DNA Center from Prefix object."""
        return super().update(attrs)

    def delete(self):
        """Delete Prefix in DNA Center from Prefix object."""
        return self


class DnaCenterIPAddress(IPAddress):
    """DNA Center implementation of IPAddress DiffSync model."""

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create IPAddress in DNA Center from IPAddress object."""
        return super().create(adapter=adapter, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update IPAddress in DNA Center from IPAddress object."""
        return super().update(attrs)

    def delete(self):
        """Delete IPAddress in DNA Center from IPAddress object."""
        return self


class DnaCenterIPAddressonInterface(IPAddressOnInterface):
    """DNA Center implementation of IPAddress DiffSync model."""

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create IPAddress in DNA Center from IPAddress object."""
        return super().create(adapter=adapter, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update IPAddress in DNA Center from IPAddress object."""
        return super().update(attrs)

    def delete(self):
        """Delete IPAddress in DNA Center from IPAddress object."""
        return self
