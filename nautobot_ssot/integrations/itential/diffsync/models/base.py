"""Itential SSoT shared diffsync models."""

from typing import Optional
from diffsync import DiffSyncModel


class BaseAnsibleDeviceDiffsyncModel(DiffSyncModel):
    """Itential Ansible Device DiffSyncModel."""

    _modelname = "device"
    _identifiers = ("name",)
    _attributes = ("variables",)

    name: str
    variables: Optional[dict]


class BaseAnsibleDefaultGroupDiffsyncModel(DiffSyncModel):
    """Itential Default Ansible Group DiffsyncModel."""

    _modelname = "all_group"
    _identifiers = ("name",)
    _attributes = ("variables",)

    name: str
    variables: Optional[dict]
