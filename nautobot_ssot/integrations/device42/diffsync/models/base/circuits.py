"""Base Circuit subclasses DiffSyncModel for nautobot_ssot_device42 data sync."""

from typing import List, Optional
from uuid import UUID

from diffsync import DiffSyncModel


class Provider(DiffSyncModel):
    """Base Provider model."""

    _modelname = "provider"
    _identifiers = ("name",)
    _attributes = ("notes", "vendor_url", "vendor_acct", "vendor_contact1", "vendor_contact2")
    _children = {}

    name: str
    notes: Optional[str] = None
    vendor_url: Optional[str] = None
    vendor_acct: Optional[str] = None
    vendor_contact1: Optional[str] = None
    vendor_contact2: Optional[str] = None
    tags: Optional[List[str]] = None
    uuid: Optional[UUID] = None


class Circuit(DiffSyncModel):
    """Base TelcoCircuit model."""

    _modelname = "circuit"
    _identifiers = (
        "circuit_id",
        "provider",
    )
    _attributes = (
        "notes",
        "type",
        "status",
        "install_date",
        "origin_int",
        "origin_dev",
        "endpoint_int",
        "endpoint_dev",
        "bandwidth",
        "tags",
    )
    _children = {}
    circuit_id: str
    provider: str
    notes: Optional[str] = None
    type: str
    status: str
    install_date: Optional[str] = None
    origin_int: Optional[str] = None
    origin_dev: Optional[str] = None
    endpoint_int: Optional[str] = None
    endpoint_dev: Optional[str] = None
    bandwidth: Optional[int] = None
    tags: Optional[List[str]] = None
    uuid: Optional[UUID] = None
