"""DiffSyncModel subclasses for Nautobot-to-Panorama data sync."""

from typing import Optional
from uuid import UUID

from diffsync import DiffSyncModel
from diffsync.enum import DiffSyncModelFlags
from nautobot.dcim.models import ControllerManagedDeviceGroup as NBControllerManagedDeviceGroup
from nautobot.dcim.models import Interface as NBInterface
from nautobot.dcim.models import InterfaceVDCAssignment as NBInterfaceVDCAssignment
from nautobot.dcim.models import SoftwareVersion as NBSoftwareVersion

from nautobot_ssot.contrib import NautobotModel
from nautobot_ssot.integrations.panorama.models import (
    VirtualDeviceContextToControllerManagedDeviceGroup as NBCmdgToVdc,
)


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


class Vdc(DiffSyncModel):
    """DiffSync model for Panorama VirtualDeviceContext."""

    _modelname = "vdc"
    _identifiers = ("parent", "name")

    name: str
    parent: str


class VirtualDeviceContextAssociation(NautobotModel):
    """Diffsync model for InterfaceVDCAssignment."""

    _model = NBInterfaceVDCAssignment
    _modelname = "virtualdevicecontextassociation"
    _identifiers = (
        "virtual_device_context__device__serial",
        "virtual_device_context__name",
        "interface__device__serial",
        "interface__name",
    )

    virtual_device_context__device__serial: str
    virtual_device_context__name: str
    interface__device__serial: str
    interface__name: str


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
    _attributes = ("parent__name",)

    name: str
    controller__name: str
    parent__name: Optional[str] = None


class DeviceToControllerManagedDeviceGroup(DiffSyncModel):
    """Diffsync model for DeviceToControllerManagedDeviceGroup."""

    _modelname = "devicetocontrollermanageddevicegroup"
    _identifiers = (
        "device__serial",
        "controllermanageddevicegroup__name",
    )

    device__serial: str
    controllermanageddevicegroup__name: str


class VdcToControllerManagedDeviceGroup(NautobotModel):
    """DiffSync model for VDC-to-CMDG association."""

    _model = NBCmdgToVdc
    _modelname = "vdctocontrollermanageddevicegroup"
    _identifiers = (
        "controller_managed_device_group__name",
        "virtual_device_context__device__serial",
        "virtual_device_context__name",
    )

    controller_managed_device_group__name: str
    virtual_device_context__device__serial: str
    virtual_device_context__name: str
