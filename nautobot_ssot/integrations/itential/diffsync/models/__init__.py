"""Itential SSoT diffsync models."""


from typing import Optional
from diffsync import DiffSyncModel


class SharedAnsibleDeviceDiffsyncModel(DiffSyncModel):
    """Itential Ansible Device DiffSyncModel."""

    _modelname = "device"
    _identifiers = ("name",)
    _attributes = ("variables",)

    name: str
    variables: Optional[dict]
