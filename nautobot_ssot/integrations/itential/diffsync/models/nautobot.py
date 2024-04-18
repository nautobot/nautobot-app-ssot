"""Itential SSoT Nautobot models."""


from nautobot_ssot.integrations.itential.diffsync.models import shared


class NautobotAnsibleDeviceModel(shared.SharedAnsibleDeviceDiffsyncModel):
    """Nautobot => Itential Ansible Device DiffSyncModel."""


class NautobotDefaultAnsibleGroupModel(shared.SharedAnsibleDefaultGroupDiffsyncModel):
    """Nautobot => Itential Default Ansible Group DiffsyncModel."""
