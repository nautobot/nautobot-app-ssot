"""Base asset subclasses DiffSyncModel for nautobot_ssot_device42 data sync."""

from typing import Optional
from uuid import UUID

from diffsync import DiffSyncModel


class PatchPanel(DiffSyncModel):
    """Base Patch Panel model."""

    _modelname = "patchpanel"
    _identifiers = ("name",)
    _attributes = (
        "in_service",
        "vendor",
        "model",
        "orientation",
        "position",
        "num_ports",
        "building",
        "room",
        "rack",
        "serial_no",
    )
    _children = {}

    name: str
    in_service: bool
    vendor: str
    model: str
    orientation: str
    position: Optional[float]
    num_ports: int
    building: Optional[str]
    room: Optional[str]
    rack: Optional[str]
    serial_no: Optional[str]
    uuid: Optional[UUID]


class PatchPanelRearPort(DiffSyncModel):
    """Base Patch Panel RearPort model."""

    _modelname = "patchpanelrearport"
    _identifiers = ("name", "patchpanel")
    _attributes = ("port_type",)
    _children = {}

    name: str
    patchpanel: str
    port_type: str
    uuid: Optional[UUID]


class PatchPanelFrontPort(DiffSyncModel):
    """Base Patch Panel FrontPort model."""

    _modelname = "patchpanelfrontport"
    _identifiers = ("name", "patchpanel")
    _attributes = ("port_type",)
    _children = {}

    name: str
    patchpanel: str
    port_type: str
    uuid: Optional[UUID]
