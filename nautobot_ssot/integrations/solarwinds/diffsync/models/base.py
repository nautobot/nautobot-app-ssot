# pylint: disable=R0801
"""DiffSyncModel subclasses for Nautobot-to-SolarWinds data sync."""

try:
    from typing import Annotated  # Python>=3.9
except ImportError:
    from typing_extensions import Annotated  # Python<3.9

from typing import List, Optional

from diffsync.enum import DiffSyncModelFlags
from nautobot.dcim.models import Device, DeviceType, Interface, Location, Manufacturer, Platform, SoftwareVersion
from nautobot.extras.models import Role
from nautobot.ipam.models import IPAddress, IPAddressToInterface, Prefix

from nautobot_ssot.contrib.model import NautobotModel
from nautobot_ssot.contrib.types import CustomFieldAnnotation
from nautobot_ssot.tests.contrib_base_classes import ContentTypeDict


class LocationModel(NautobotModel):
    """Diffsync model for SolarWinds containers."""

    model_flags: DiffSyncModelFlags = DiffSyncModelFlags.SKIP_UNMATCHED_DST

    _model = Location
    _modelname = "location"
    _identifiers = (
        "name",
        "location_type__name",
        "parent__name",
        "parent__location_type__name",
        "parent__parent__name",
        "parent__parent__location_type__name",
    )
    _attributes = ("status__name",)
    _children = {}

    name: str
    location_type__name: str
    status__name: str
    parent__name: Optional[str] = None
    parent__location_type__name: Optional[str] = None
    parent__parent__name: Optional[str] = None
    parent__parent__location_type__name: Optional[str] = None


class DeviceTypeModel(NautobotModel):
    """DiffSync model for SolarWinds device types."""

    model_flags: DiffSyncModelFlags = DiffSyncModelFlags.SKIP_UNMATCHED_DST

    _model = DeviceType
    _modelname = "device_type"
    _identifiers = ("model", "manufacturer__name")

    model: str
    manufacturer__name: str


class ManufacturerModel(NautobotModel):
    """DiffSync model for SolarWinds device manufacturers."""

    model_flags: DiffSyncModelFlags = DiffSyncModelFlags.SKIP_UNMATCHED_DST

    _model = Manufacturer
    _modelname = "manufacturer"
    _identifiers = ("name",)
    _children = {"device_type": "device_types"}

    name: str
    device_types: List[DeviceTypeModel] = []


class PlatformModel(NautobotModel):
    """Shared data model representing a Platform in either of the local or remote Nautobot instances."""

    model_flags: DiffSyncModelFlags = DiffSyncModelFlags.SKIP_UNMATCHED_DST

    _model = Platform
    _modelname = "platform"
    _identifiers = ("name", "manufacturer__name")
    _attributes = ("network_driver", "napalm_driver")

    name: str
    manufacturer__name: str
    network_driver: str
    napalm_driver: str


class RoleModel(NautobotModel):
    """DiffSync model for SolarWinds Device roles."""

    model_flags: DiffSyncModelFlags = DiffSyncModelFlags.SKIP_UNMATCHED_DST

    _model = Role
    _modelname = "role"
    _identifiers = ("name",)
    _attributes = ("content_types",)

    name: str
    content_types: List[ContentTypeDict] = []


class SoftwareVersionModel(NautobotModel):
    """DiffSync model for SolarWinds Device Software versions."""

    model_flags: DiffSyncModelFlags = DiffSyncModelFlags.SKIP_UNMATCHED_DST

    _model = SoftwareVersion
    _modelname = "softwareversion"
    _identifiers = ("version", "platform__name")
    _attributes = ("status__name",)

    version: str
    platform__name: str
    status__name: str


class DeviceModel(NautobotModel):
    """DiffSync model for SolarWinds devices."""

    _model = Device
    _modelname = "device"
    _identifiers = ("name",)
    _attributes = (
        "status__name",
        "device_type__manufacturer__name",
        "device_type__model",
        "location__name",
        "location__location_type__name",
        "platform__name",
        "role__name",
        "serial",
        "snmp_location",
        "software_version__version",
        "software_version__platform__name",
        "last_synced_from_sor",
        "system_of_record",
        "tenant__name",
    )
    _children = {"interface": "interfaces"}

    name: str
    device_type__manufacturer__name: str
    device_type__model: str
    location__name: str
    location__location_type__name: str
    platform__name: str
    role__name: str
    serial: str
    software_version__version: Optional[str] = None
    software_version__platform__name: Optional[str] = None
    status__name: str
    tenant__name: Optional[str] = None

    interfaces: Optional[List["InterfaceModel"]] = []

    snmp_location: Annotated[Optional[str], CustomFieldAnnotation(name="snmp_location")] = None
    system_of_record: Annotated[Optional[str], CustomFieldAnnotation(name="system_of_record")] = None
    last_synced_from_sor: Annotated[Optional[str], CustomFieldAnnotation(name="last_synced_from_sor")] = None

    @classmethod
    def get_queryset(cls):
        """Return only Devices with system_of_record set to SolarWinds."""
        return Device.objects.filter(_custom_field_data__system_of_record="SolarWinds")


class InterfaceModel(NautobotModel):
    """Shared data model representing an Interface."""

    # Metadata about this model
    _model = Interface
    _modelname = "interface"
    _identifiers = ("name", "device__name")
    _attributes = (
        "enabled",
        "mac_address",
        "mtu",
        "type",
        "status__name",
    )
    _children = {}

    name: str
    device__name: str
    enabled: bool
    mac_address: Optional[str] = None
    mtu: int
    type: str
    status__name: str

    @classmethod
    def get_queryset(cls):
        """Return only Interfaces with system_of_record set to SolarWinds."""
        return Interface.objects.filter(device___custom_field_data__system_of_record="SolarWinds")


class PrefixModel(NautobotModel):
    """Shared data model representing a Prefix."""

    # Metadata about this model
    _model = Prefix
    _modelname = "prefix"
    _identifiers = (
        "network",
        "prefix_length",
        "namespace__name",
    )
    _attributes = (
        "status__name",
        "tenant__name",
        "last_synced_from_sor",
        "system_of_record",
    )

    # Data type declarations for all identifiers and attributes
    network: str
    prefix_length: int
    status__name: str
    tenant__name: Optional[str] = None
    namespace__name: str
    system_of_record: Annotated[Optional[str], CustomFieldAnnotation(name="system_of_record")] = None
    last_synced_from_sor: Annotated[Optional[str], CustomFieldAnnotation(name="last_synced_from_sor")] = None

    @classmethod
    def get_queryset(cls):
        """Return only Prefixes with system_of_record set to SolarWinds."""
        return Prefix.objects.filter(_custom_field_data__system_of_record="SolarWinds")


class IPAddressModel(NautobotModel):
    """Shared data model representing an IPAddress."""

    _model = IPAddress
    _modelname = "ipaddress"
    _identifiers = (
        "host",
        "parent__network",
        "parent__prefix_length",
        "parent__namespace__name",
    )
    _attributes = (
        "mask_length",
        "status__name",
        "ip_version",
        "tenant__name",
        "last_synced_from_sor",
        "system_of_record",
    )

    host: str
    mask_length: int
    parent__network: str
    parent__prefix_length: int
    parent__namespace__name: str
    status__name: str
    ip_version: int
    tenant__name: Optional[str] = None
    system_of_record: Annotated[Optional[str], CustomFieldAnnotation(name="system_of_record")] = None
    last_synced_from_sor: Annotated[Optional[str], CustomFieldAnnotation(name="last_synced_from_sor")] = None

    @classmethod
    def get_queryset(cls):
        """Return only IP Addresses with system_of_record set to SolarWinds."""
        return IPAddress.objects.filter(_custom_field_data__system_of_record="SolarWinds")


class IPAddressToInterfaceModel(NautobotModel):
    """Shared data model representing an IPAddressToInterface."""

    _model = IPAddressToInterface
    _modelname = "ipassignment"
    _identifiers = ("interface__device__name", "interface__name", "ip_address__host")
    _attributes = (
        "interface__device__primary_ip4__host",
        "interface__device__primary_ip6__host",
    )
    _children = {}

    interface__device__name: str
    interface__name: str
    ip_address__host: str
    interface__device__primary_ip4__host: Optional[str] = None
    interface__device__primary_ip6__host: Optional[str] = None

    @classmethod
    def get_queryset(cls):
        """Return only IPAddressToInterface with system_of_record set to SolarWinds."""
        return IPAddressToInterface.objects.filter(interface__device___custom_field_data__system_of_record="SolarWinds")
