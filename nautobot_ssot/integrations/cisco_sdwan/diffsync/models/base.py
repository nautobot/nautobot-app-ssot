"""Base DiffSync models for the Cisco SD-WAN SSoT integration."""

from typing import Optional

from diffsync.enum import DiffSyncModelFlags
from nautobot.dcim.models import Device as NBDevice
from nautobot.dcim.models import DeviceType as NBDeviceType
from nautobot.dcim.models import Interface as NBInterface
from nautobot.dcim.models import SoftwareVersion as NBSoftwareVersion
from nautobot.ipam.models import IPAddressToInterface as NBIPAddressToInterface

from nautobot_ssot.contrib import NautobotModel


class DeviceType(NautobotModel):
    """DiffSync model for Nautobot DeviceType."""

    model_flags: DiffSyncModelFlags = DiffSyncModelFlags.SKIP_UNMATCHED_DST

    _model = NBDeviceType
    _modelname = "device_type"
    _identifiers = (
        "model",
        "manufacturer__name",
    )
    _attributes = ("part_number",)

    model: str
    manufacturer__name: str
    part_number: Optional[str] = ""


class Device(NautobotModel):
    """DiffSync model for Nautobot Device."""

    _model = NBDevice
    _modelname = "device"
    _identifiers = ("name",)
    _attributes = (
        "status__name",
        "role__name",
        "device_type__model",
        "platform__name",
        "location__name",
        "serial",
        "secrets_group__name",
        "tenant__name",
        "software_version__version",
        "software_version__platform__name",
    )

    name: str
    status__name: Optional[str] = None
    role__name: Optional[str] = None
    device_type__model: Optional[str] = None
    platform__name: Optional[str] = None
    location__name: Optional[str] = None
    serial: Optional[str] = None
    secrets_group__name: Optional[str] = None
    tenant__name: Optional[str] = None
    software_version__version: Optional[str] = None
    software_version__platform__name: Optional[str] = None


class Interface(NautobotModel):
    """DiffSync model for Nautobot Interface."""

    _modelname = "interface"
    _model = NBInterface
    _identifiers = (
        "device__name",
        "name",
    )
    _attributes = (
        "status__name",
        "type",
        "description",
        "enabled",
        "mtu",
    )

    device__name: str
    name: str
    status__name: Optional[str] = None
    type: Optional[str] = None
    description: Optional[str] = None
    mtu: Optional[int] = None
    enabled: Optional[bool] = False


class IPAddressToInterface(NautobotModel):
    """DiffSync model for Nautobot IPAddressToInterface."""

    _model = NBIPAddressToInterface
    _modelname = "ip_address_to_interface"
    _identifiers = (
        "interface__device__name",
        "interface__name",
        "ip_address__host",
        "ip_address__mask_length",
    )
    _attributes = ("interface__vrf__name",)

    interface__device__name: str
    interface__name: str
    ip_address__host: str
    ip_address__mask_length: int
    interface__vrf__name: Optional[str] = None


class SoftwareVersion(NautobotModel):
    """DiffSync model for Nautobot SoftwareVersion."""

    model_flags: DiffSyncModelFlags = DiffSyncModelFlags.SKIP_UNMATCHED_DST

    _modelname = "software_version"
    _model = NBSoftwareVersion
    _identifiers = (
        "platform__name",
        "version",
        "status__name",
    )

    platform__name: str
    version: str
    status__name: str
