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
    position: Optional[float] = None
    num_ports: int
    building: Optional[str] = None
    room: Optional[str] = None
    rack: Optional[str] = None
    serial_no: Optional[str] = None
    uuid: Optional[UUID] = None


class PatchPanelRearPort(DiffSyncModel):
    """Base Patch Panel RearPort model."""

    _modelname = "patchpanelrearport"
    _identifiers = ("name", "patchpanel")
    _attributes = ("port_type",)
    _children = {}

    name: str
    patchpanel: str
    port_type: str
    uuid: Optional[UUID] = None


class PatchPanelFrontPort(DiffSyncModel):
    """Base Patch Panel FrontPort model."""

    _modelname = "patchpanelfrontport"
    _identifiers = ("name", "patchpanel")
    _attributes = ("port_type",)
    _children = {}

    name: str
    patchpanel: str
    port_type: str
    uuid: Optional[UUID] = None
