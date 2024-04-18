"""Itential SSoT Nautobot models."""


from nautobot_ssot.integrations.itential.diffsync.models import SharedAnsibleDeviceDiffsyncModel


class NautobotAnsibleDeviceModel(SharedAnsibleDeviceDiffsyncModel):
    """Nautobot => Itential Ansible Device DiffSyncModel."""
