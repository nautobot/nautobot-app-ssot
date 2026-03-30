"""DiffSyncModel subclasses for Nautobot-to-Panorama data sync."""

from typing import Optional
from uuid import UUID

from diffsync import DiffSyncModel
from diffsync.enum import DiffSyncModelFlags
from nautobot.dcim.models import ControllerManagedDeviceGroup as NBControllerManagedDeviceGroup
from nautobot.dcim.models import Interface as NBInterface
from nautobot.dcim.models import SoftwareVersion as NBSoftwareVersion

from nautobot_ssot.contrib import NautobotModel
from nautobot_ssot.integrations.panorama.models import LogicalGroupToDevice as NBLogicalGroupToDevice
from nautobot_ssot.integrations.panorama.models import LogicalGroupToVirtualSystem as NBLogicalGroupToVirtualSystem
from nautobot_ssot.integrations.panorama.models import VirtualSystemAssociation as NBVirtualSystemAssociation


class Firewall(DiffSyncModel):
    """DiffSync model for Panorama Firewall."""

    model_flags: DiffSyncModelFlags = DiffSyncModelFlags.SKIP_UNMATCHED_DST

    _modelname = "firewall"
    _identifiers = ("serial",)
    _attributes = ("name", "model", "management_ip", "management_interface_name")

    name: str
    serial: str
    model: str
    management_ip: Optional[str] = None
    management_interface_name: Optional[str] = None


class FirewallInterface(NautobotModel):
    """Shared data model representing an Interface."""

    _modelname = "firewall_interface"
    _model = NBInterface
    _identifiers = (
        "device__serial",
        "name",
    )
    _attributes = (
        "status__name",
        "type",
        "description",
    )

    device__serial: str
    name: str

    status__name: Optional[str] = None
    type: Optional[str] = None
    description: Optional[str] = None

    pk: Optional[UUID] = None

    _children = {}


class IPAddressToInterface(DiffSyncModel):
    """Diffsync model for IPAddressToInterface."""

    _modelname = "ip_address_to_interface"
    _identifiers = ("interface__device__serial", "interface__name", "ip_address__host", "ip_address__mask_length")

    interface__device__serial: str
    interface__name: str
    ip_address__host: str
    ip_address__mask_length: str


class SoftwareVersion(NautobotModel):
    """DiffSync model for Software data (Nautobot core model)."""

    model_flags: DiffSyncModelFlags = DiffSyncModelFlags.SKIP_UNMATCHED_DST

    _modelname = "softwareversion"
    _model = NBSoftwareVersion
    _identifiers = (
        "platform__name",
        "version",
        "status__name",
    )
    platform__name: str
    version: str
    status__name: str


class SoftwareVersionToDevice(DiffSyncModel):
    """DiffSync model for SoftwareVersionToDevice."""

    _modelname = "softwareversiontodevice"
    _identifiers = (
        "device__serial",
        "platform__name",
        "version",
    )

    device__serial: str
    platform__name: str
    version: str


class Vsys(DiffSyncModel):
    """DiffSync model for Panorama Vsys."""

    _modelname = "vsys"
    _identifiers = ("parent", "name")

    name: str
    parent: str


class VirtualSystemAssociation(NautobotModel):
    """Diffsync model for VirtualSystemAssociation."""

    _model = NBVirtualSystemAssociation
    _modelname = "virtualsystemassociation"
    _identifiers = ("vsys__device__serial", "vsys__name", "iface__device__serial", "iface__name")

    vsys__device__serial: str
    vsys__name: str
    iface__device__serial: str
    iface__name: str


class LogicalGroup(DiffSyncModel):
    """DiffSync model for Panorama LogicalGroup."""

    model_flags: DiffSyncModelFlags = DiffSyncModelFlags.SKIP_UNMATCHED_DST

    _modelname = "logicalgroup"
    _identifiers = ("name",)
    _attributes = ("parent", "panorama")

    name: str
    panorama: Optional[str] = None
    parent: Optional[str] = None


class LogicalGroupToVirtualSystem(NautobotModel):
    """Diffsync model for LogicalGroupToVirtualSystem."""

    _model = NBLogicalGroupToVirtualSystem
    _modelname = "logicalgrouptovirtualsystem"
    _identifiers = ("group__name", "vsys__device__serial", "vsys__name")

    group__name: str
    vsys__device__serial: str
    vsys__name: str


class LogicalGroupToDevice(NautobotModel):
    """Diffsync model for LogicalGroupToDevice."""

    _model = NBLogicalGroupToDevice
    _modelname = "logicalgrouptodevice"
    _identifiers = ("group__name", "device__serial")

    group__name: str
    device__serial: str


class DeviceType(DiffSyncModel):
    """Diffsync model for Nautobot DeviceType."""

    model_flags: DiffSyncModelFlags = DiffSyncModelFlags.SKIP_UNMATCHED_DST

    _modelname = "device_type"
    _identifiers = ("model", "manufacturer__name")
    _attributes = ("part_number",)

    model: str
    manufacturer__name: str
    part_number: Optional[str] = None


class ControllerManagedDeviceGroup(NautobotModel):
    """Diffsync model for ControllerManagedDeviceGroup."""

    model_flags: DiffSyncModelFlags = DiffSyncModelFlags.SKIP_UNMATCHED_DST

    _model = NBControllerManagedDeviceGroup
    _modelname = "controllermanageddevicegroup"
    _identifiers = ("name", "controller__name")

    name: str
    controller__name: str


class DeviceToControllerManagedDeviceGroup(DiffSyncModel):
    """Diffsync model for DeviceToControllerManagedDeviceGroup."""

    _modelname = "devicetocontrollermanageddevicegroup"
    _identifiers = (
        "device__serial",
        "controllermanageddevicegroup__name",
    )

    device__serial: str
    controllermanageddevicegroup__name: str
