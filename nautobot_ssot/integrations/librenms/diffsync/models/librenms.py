"""Nautobot Ssot Librenms DiffSync models for Nautobot Ssot Librenms SSoT."""

from nautobot_ssot.integrations.librenms.diffsync.models.base import Device, Location


class LibrenmsLocation(Location):
    """LibreNMS implementation of Location DiffSync model."""

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create Location in LibreNMS from LibrenmsLocation object."""
        return super().create(diffsync=diffsync, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update Location in LibreNMS from LibrenmsLocation object."""
        return super().update(attrs)

    def delete(self):
        """Delete Location in LibreNMS from LibrenmsLocation object."""
        return self


class LibrenmsDevice(Device):
    """LibreNMS implementation of Device DiffSync model."""

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create Device in LibreNMS from LibrenmsDevice object."""
        return super().create(diffsync=diffsync, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update Device in LibreNMS from LibrenmsDevice object."""
        return super().update(attrs)

    def delete(self):
        """Delete Device in LibreNMS from LibrenmsDevice object."""
        return self
