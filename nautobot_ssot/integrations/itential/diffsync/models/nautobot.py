"""Itential SSoT Nautobot models."""

from diffsync import DiffSyncModel
from typing import Optional


class NautobotAnsibleDeviceModel(DiffSyncModel):
    """Nautobot => Itential Ansible Device DiffSyncModel."""

    _modelname = "device"
    _identifiers = ("name",)
    _attributes = ("variables",)

    name: str
    variables: Optional[dict]
