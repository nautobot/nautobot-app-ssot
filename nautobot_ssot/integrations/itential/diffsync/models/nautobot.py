"""Itential SSoT Nautobot models."""

from nautobot_ssot.integrations.itential.diffsync.models import base


class NautobotAnsibleDeviceModel(base.BaseAnsibleDeviceDiffsyncModel):
    """Nautobot => Itential Ansible Device DiffSyncModel."""

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create device in Nautobot.."""
        raise NotImplementedError

    def update(self, attrs):
        """Update device in Nautobot."""
        raise NotImplementedError

    def delete(self):
        """Delete device in Nautobot."""
        raise NotImplementedError


class NautobotDefaultAnsibleGroupModel(base.BaseAnsibleDefaultGroupDiffsyncModel):
    """Nautobot => Itential Default Ansible Group DiffsyncModel."""

    @classmethod
    def create(cls, diffsync, ids, attrs):
        """Create default group in Nautobot.."""
        raise NotImplementedError

    def update(self, attrs):
        """Update default group in Nautobot."""
        raise NotImplementedError

    def delete(self):
        """Delete default group in Nautobot."""
        raise NotImplementedError
