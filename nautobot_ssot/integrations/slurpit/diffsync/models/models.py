# pylint: disable=R0801
"""Data models for the DiffSync integration."""

from typing import List, Optional, Union

try:
    from typing import Annotated  # Python>=3.9
except ImportError:
    from typing_extensions import Annotated


from django.core.exceptions import ObjectDoesNotExist
from nautobot.dcim.models import Device, DeviceType, Interface, InventoryItem, Location, Manufacturer, Platform
from nautobot.extras.models import Role
from nautobot.ipam.models import VLAN, VRF, IPAddress, IPAddressToInterface, Prefix
from netaddr import EUI
from pydantic import field_serializer
from typing_extensions import TypedDict  # pylint: disable=C0412

from nautobot_ssot.contrib import CustomFieldAnnotation, NautobotModel
from nautobot_ssot.integrations.slurpit import constants
from nautobot_ssot.tests.contrib_base_classes import ContentTypeDict, TagDict


class ModelQuerySetMixin:
    """Mixin only getting objects that are tagged."""

    @classmethod
    def get_queryset(cls, data):
        """Get the queryset for the model."""
        tagged = data.get("sync_slurpit_tagged_only")
        if tagged and hasattr(cls._model, "_custom_field_data"):
            if hasattr(cls._model, "tags"):
                return cls._model.objects.filter(tags__name="SSoT Synced from Slurpit")
            return cls._model.objects.filter(_custom_field_data__system_of_record="Slurpit")
        return cls._model.objects.all()

    @classmethod
    def _get_queryset(cls, data):
        """Get the queryset used to load the models data from Nautobot."""
        available_fields = {field.name for field in cls._model._meta.get_fields()}
        parameter_names = [
            parameter for parameter in list(cls._identifiers) + list(cls._attributes) if parameter in available_fields
        ]
        # Here we identify any foreign keys (i.e. fields with '__' in them) so that we can load them directly in the
        # first query if this function hasn't been overridden.
        prefetch_related_parameters = [parameter.split("__")[0] for parameter in parameter_names if "__" in parameter]
        qs = cls.get_queryset(data=data)
        return qs.prefetch_related(*prefetch_related_parameters)


class LocationModel(ModelQuerySetMixin, NautobotModel):
    """Data model representing a Location."""

    _model = Location
    _modelname = "location"
    _identifiers = ("name",)
    _attributes = (
        "location_type__name",
        "description",
        "status__name",
        "contact_phone",
        "physical_address",
        "latitude",
        "longitude",
        "tags",
        "system_of_record",
        "last_synced_from_sor",
    )

    name: str
    description: Optional[str]
    location_type__name: str
    status__name: str
    contact_phone: Optional[str]
    physical_address: Optional[str]
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    tags: List[TagDict] = []
    system_of_record: Annotated[
        Optional[str], CustomFieldAnnotation(name="system_of_record", key="system_of_record")
    ] = None
    last_synced_from_sor: Annotated[
        Optional[str], CustomFieldAnnotation(name="last_synced_from_sor", key="last_synced_from_sor")
    ] = None


class ManufacturerModel(ModelQuerySetMixin, NautobotModel):
    """Data model representing a Manufacturer."""

    _model = Manufacturer
    _modelname = "manufacturer"
    _identifiers = ("name",)
    _attributes = ("system_of_record", "last_synced_from_sor")

    name: str
    system_of_record: Annotated[
        Optional[str], CustomFieldAnnotation(name="system_of_record", key="system_of_record")
    ] = None
    last_synced_from_sor: Annotated[
        Optional[str], CustomFieldAnnotation(name="last_synced_from_sor", key="last_synced_from_sor")
    ] = None


class DeviceTypeModel(ModelQuerySetMixin, NautobotModel):
    """Data model representing a DeviceType."""

    _model = DeviceType
    _modelname = "device_type"
    _identifiers = ("model", "manufacturer__name")
    _attributes = ("tags", "system_of_record", "last_synced_from_sor")

    model: str
    manufacturer__name: str
    tags: List[TagDict] = []
    system_of_record: Annotated[
        Optional[str], CustomFieldAnnotation(name="system_of_record", key="system_of_record")
    ] = None
    last_synced_from_sor: Annotated[
        Optional[str], CustomFieldAnnotation(name="last_synced_from_sor", key="last_synced_from_sor")
    ] = None


class PlatformModel(ModelQuerySetMixin, NautobotModel):
    """Data model representing a Platform."""

    _model = Platform
    _modelname = "platform"
    _identifiers = ("name", "manufacturer__name")
    _attributes = ("network_driver", "system_of_record", "last_synced_from_sor")

    name: str
    manufacturer__name: str
    network_driver: str
    system_of_record: Annotated[
        Optional[str], CustomFieldAnnotation(name="system_of_record", key="system_of_record")
    ] = None
    last_synced_from_sor: Annotated[
        Optional[str], CustomFieldAnnotation(name="last_synced_from_sor", key="last_synced_from_sor")
    ] = None


class RoleModel(ModelQuerySetMixin, NautobotModel):
    """Data model representing a Role."""

    _model = Role
    _modelname = "role"
    _identifiers = ("name",)
    _attributes = (
        "content_types",
        "color",
        "system_of_record",
        "last_synced_from_sor",
    )

    name: str
    color: Optional[str]
    content_types: List[ContentTypeDict] = []
    system_of_record: Annotated[
        Optional[str], CustomFieldAnnotation(name="system_of_record", key="system_of_record")
    ] = None
    last_synced_from_sor: Annotated[
        Optional[str], CustomFieldAnnotation(name="last_synced_from_sor", key="last_synced_from_sor")
    ] = None

    @classmethod
    def get_queryset(cls, data=None):
        """Get the queryset for the Role model."""
        return cls._model.objects.filter(name=constants.DEFAULT_DEVICE_ROLE)


class DeviceModel(ModelQuerySetMixin, NautobotModel):
    """Data model representing a Device."""

    _model = Device
    _modelname = "device"
    _identifiers = ("name",)
    _attributes = (
        "location__name",
        "location__parent__name",
        "location__location_type__name",
        "location__parent__location_type__name",
        "device_type__manufacturer__name",
        "device_type__model",
        "platform__name",
        "role__name",
        "serial",
        "status__name",
        "tags",
        "system_of_record",
        "last_synced_from_sor",
    )
    _children = {"inventory_item": "inventory_items"}

    name: str
    location__name: Optional[str] = None
    location__location_type__name: Optional[str] = None
    location__parent__name: Optional[str] = None
    location__parent__location_type__name: Optional[str] = None
    device_type__manufacturer__name: str
    device_type__model: str
    platform__name: Optional[str] = None
    role__name: str
    serial: Optional[str] = ""
    status__name: str
    inventory_items: List["InventoryItemModel"] = []
    tags: List[TagDict] = []
    system_of_record: Annotated[
        Optional[str], CustomFieldAnnotation(name="system_of_record", key="system_of_record")
    ] = None
    last_synced_from_sor: Annotated[
        Optional[str], CustomFieldAnnotation(name="last_synced_from_sor", key="last_synced_from_sor")
    ] = None


class InventoryItemModel(ModelQuerySetMixin, NautobotModel):
    """Data model representing an InventoryItem."""

    _model = InventoryItem
    _modelname = "inventory_item"
    _identifiers = ("name", "device__name")
    _attributes = (
        "description",
        "part_id",
        "serial",
        "tags",
        "system_of_record",
        "last_synced_from_sor",
    )

    name: str
    part_id: Optional[str]
    serial: Optional[str]
    description: Optional[str]
    device__name: str
    tags: List[TagDict] = []
    system_of_record: Annotated[
        Optional[str], CustomFieldAnnotation(name="system_of_record", key="system_of_record")
    ] = None
    last_synced_from_sor: Annotated[
        Optional[str], CustomFieldAnnotation(name="last_synced_from_sor", key="last_synced_from_sor")
    ] = None


class VLANModel(ModelQuerySetMixin, NautobotModel):
    """Data model representing a VLAN."""

    _model = VLAN
    _modelname = "vlan"
    _identifiers = ("vid", "name")
    _attributes = ("status__name", "tags", "system_of_record", "last_synced_from_sor")

    vid: int
    name: str
    status__name: str
    tags: List[TagDict] = []
    system_of_record: Annotated[
        Optional[str], CustomFieldAnnotation(name="system_of_record", key="system_of_record")
    ] = None
    last_synced_from_sor: Annotated[
        Optional[str], CustomFieldAnnotation(name="last_synced_from_sor", key="last_synced_from_sor")
    ] = None


class VRFModel(ModelQuerySetMixin, NautobotModel):
    """data model representing a VRF."""

    _model = VRF
    _modelname = "vrf"
    _identifiers = ("name",)
    _attributes = ("namespace__name", "tags", "system_of_record", "last_synced_from_sor")

    name: str
    namespace__name: str
    tags: List[TagDict] = []
    system_of_record: Annotated[
        Optional[str], CustomFieldAnnotation(name="system_of_record", key="system_of_record")
    ] = None
    last_synced_from_sor: Annotated[
        Optional[str], CustomFieldAnnotation(name="last_synced_from_sor", key="last_synced_from_sor")
    ] = None


class VRFDict(TypedDict):
    """TypedDict for VRF data."""

    name: str


class PrefixModel(ModelQuerySetMixin, NautobotModel):
    """Data model representing a Prefix."""

    _model = Prefix
    _modelname = "prefix"
    _identifiers = ("network",)
    _attributes = (
        "prefix_length",
        "status__name",
        "namespace__name",
        "vrfs",
        "tags",
        "system_of_record",
        "last_synced_from_sor",
    )

    network: str
    prefix_length: int
    status__name: str
    namespace__name: str
    vrfs: List[VRFDict] = []
    tags: List[TagDict] = []
    system_of_record: Annotated[
        Optional[str], CustomFieldAnnotation(name="system_of_record", key="system_of_record")
    ] = None
    last_synced_from_sor: Annotated[
        Optional[str], CustomFieldAnnotation(name="last_synced_from_sor", key="last_synced_from_sor")
    ] = None


class IPAddressModel(ModelQuerySetMixin, NautobotModel):
    """Data model representing an IPAddress."""

    _model = IPAddress
    _modelname = "ipaddress"
    _identifiers = ("host", "mask_length")
    _attributes = ("status__name", "tags", "system_of_record", "last_synced_from_sor")

    host: str
    mask_length: int
    status__name: str
    tags: List[TagDict] = []
    system_of_record: Annotated[
        Optional[str], CustomFieldAnnotation(name="system_of_record", key="system_of_record")
    ] = None
    last_synced_from_sor: Annotated[
        Optional[str], CustomFieldAnnotation(name="last_synced_from_sor", key="last_synced_from_sor")
    ] = None


class InterfaceModel(ModelQuerySetMixin, NautobotModel):
    """Data model representing an Interface."""

    _model = Interface
    _modelname = "interface"
    _identifiers = ("name", "device__name")
    _attributes = (
        "description",
        "enabled",
        "mac_address",
        "mgmt_only",
        "mtu",
        "type",
        "status__name",
        "tags",
        "system_of_record",
        "last_synced_from_sor",
    )

    device__name: str
    description: Optional[str] = ""
    enabled: bool
    mac_address: Optional[Union[str, EUI]] = ""
    mgmt_only: bool
    mtu: Optional[int]
    name: str
    type: str
    status__name: str
    tags: List[TagDict] = []
    system_of_record: Annotated[
        Optional[str], CustomFieldAnnotation(name="system_of_record", key="system_of_record")
    ] = None
    last_synced_from_sor: Annotated[
        Optional[str], CustomFieldAnnotation(name="last_synced_from_sor", key="last_synced_from_sor")
    ] = None

    @field_serializer("mac_address")
    def serialize_mac_address(self, value):
        """Serialize a MAC address to a string."""
        return str(value)


class IPAddressToInterfaceModel(ModelQuerySetMixin, NautobotModel):
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


class NautobotIPAddressToInterfaceModel(IPAddressToInterfaceModel):
    """IPAddressToInterface model for Nautobot."""

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create IPAddressToInterface in Nautobot."""
        if adapter.job.logger.debug:
            adapter.job.logger.debug(f"Creating IPAddressToInterface {ids} {attrs}")
        intf = Interface.objects.get(name=ids["interface__name"], device__name=ids["interface__device__name"])

        try:
            ip_address = IPAddress.objects.get(host=ids["ip_address__host"], tenant=intf.device.tenant)
        except ObjectDoesNotExist:
            adapter.job.logger.info(f"Unable to find IP {ids['ip_address__host']}")
            return super().create_base(adapter=adapter, ids=ids, attrs=attrs)

        obj = IPAddressToInterface(
            ip_address=ip_address,
            interface=intf,
        )
        obj.validated_save()
        if (
            attrs.get("interface__device__primary_ip4__host")
            and ids["ip_address__host"] == attrs["interface__device__primary_ip4__host"]
        ):
            obj.interface.device.primary_ip4 = IPAddress.objects.get(
                host=attrs["interface__device__primary_ip4__host"],
                tenant=obj.interface.device.tenant,
            )
            obj.interface.device.validated_save()
        if (
            attrs.get("interface__device__primary_ip6__host")
            and ids["ip_address__host"] == attrs["interface__device__primary_ip6__host"]
        ):
            obj.interface.device.primary_ip6 = IPAddress.objects.get(
                host=attrs["interface__device__primary_ip6__host"],
                tenant=obj.interface.device.tenant,
            )
            obj.interface.device.validated_save()
        return super().create_base(adapter=adapter, ids=ids, attrs=attrs)

    def update(self, attrs):
        """Update IPAddressToInterface in Nautobot."""
        obj = self.get_from_db()
        if (
            attrs.get("interface__device__primary_ip4__host")
            and self.ip_address__host == attrs["interface__device__primary_ip4__host"]
        ):
            obj.interface.device.primary_ip4 = IPAddress.objects.get(
                host=attrs["interface__device__primary_ip4__host"], tenant=obj.interface.device.tenant
            )
            obj.interface.device.validated_save()
        if (
            attrs.get("interface__device__primary_ip6__host")
            and self.ip_address__host == attrs["interface__device__primary_ip6__host"]
        ):
            obj.interface.device.primary_ip6 = IPAddress.objects.get(
                host=attrs["interface__device__primary_ip6__host"], tenant=obj.interface.device.tenant
            )
            obj.interface.device.validated_save()
        return super().update_base(attrs)

    def delete(self):
        """Delete IPAddressToInterface in Nautobot."""
        return super().delete_base()
