"""Base classes for contrib testing."""

from typing import Annotated, List, Optional
from unittest.mock import MagicMock

import nautobot.circuits.models as circuits_models
import nautobot.dcim.models as dcim_models
import nautobot.extras.models as extras_models
import nautobot.ipam.models as ipam_models
import nautobot.tenancy.models as tenancy_models
from django.contrib.contenttypes.models import ContentType
from nautobot.apps.testing import TestCase
from nautobot.dcim.choices import InterfaceTypeChoices
from nautobot.extras.management import populate_status_choices
from typing_extensions import TypedDict

from nautobot_ssot.contrib import (
    CustomRelationshipAnnotation,
    NautobotAdapter,
    NautobotModel,
    RelationshipSideEnum,
)


class TestCaseWithDeviceData(TestCase):
    """Creates device data."""

    @classmethod
    def setUpTestData(cls):
        populate_status_choices()
        cls.status_active = extras_models.Status.objects.get(name="Active")
        cls.device_role = extras_models.Role.objects.create(name="Switch")
        cls.device_role.content_types.set([ContentType.objects.get_for_model(dcim_models.Device)])
        cls.manufacturer = dcim_models.Manufacturer.objects.create(name="Generic Inc.")
        cls.device_type = dcim_models.DeviceType.objects.create(model="Generic Switch", manufacturer=cls.manufacturer)
        cls.location_type, _ = dcim_models.LocationType.objects.get_or_create(name="Site")
        cls.location_type.content_types.add(ContentType.objects.get_for_model(dcim_models.Device))
        cls.location = dcim_models.Location.objects.create(
            name="Bremen",
            location_type=cls.location_type,
            status=cls.status_active,
        )
        for name in ["sw01", "sw02"]:
            device = dcim_models.Device.objects.create(
                status=cls.status_active,
                location=cls.location,
                name=name,
                role=cls.device_role,
                device_type=cls.device_type,
            )
            dcim_models.Interface.objects.create(
                device=device,
                name="Loopback 1",
                type=InterfaceTypeChoices.TYPE_VIRTUAL,
                status=cls.status_active,
            )
            dcim_models.Interface.objects.create(
                device=device,
                name="Ethernet1",
                type=InterfaceTypeChoices.TYPE_1GE_FIXED,
                status=cls.status_active,
            )
        cls.namespace, _ = ipam_models.Namespace.objects.get_or_create(name="Global")
        cls.prefix = ipam_models.Prefix.objects.create(
            prefix="192.0.2.0/24", namespace=cls.namespace, status=cls.status_active
        )
        cls.ip_address_1 = ipam_models.IPAddress(
            address="192.0.2.1/24",
            namespace=cls.namespace,
            status=cls.status_active,
        )
        cls.ip_address_1.save()
        cls.ip_address_2 = ipam_models.IPAddress.objects.create(
            address="192.0.2.2/24",
            namespace=cls.namespace,
            status=cls.status_active,
        )
        cls.ip_address_2.save()
        super().setUpTestData()


class TagDict(TypedDict):
    """Many-to-many relationship typed dict explaining which fields are interesting."""

    name: str


class NautobotTenant(NautobotModel):
    """A tenant model for testing the `NautobotModel` base class."""

    _model = tenancy_models.Tenant
    _modelname = "tenant"
    _identifiers = ("name",)
    _attributes = ("description", "tenant_group__name", "tags")

    name: str
    description: Optional[str] = None
    tenant_group__name: Optional[str] = None
    tags: List[TagDict] = []


class NautobotTenantGroup(NautobotModel):
    """A tenant group model for testing the `NautobotModel` base class."""

    _model = tenancy_models.TenantGroup
    _modelname = "tenant_group"
    _identifiers = ("name",)
    _attributes = ("description",)
    _children = {"tenant": "tenants"}

    name: str
    description: str
    tenants: List[NautobotTenant] = []


class NautobotDeviceBay(NautobotModel):
    """A Device may model for testing the `NautobotModel` base class."""

    _model = dcim_models.DeviceBay
    _modelname = "device_bay"
    _identifiers = ("name", "device__name")
    _attributes = ("installed_device__name",)

    name: str
    device__name: str
    installed_device__name: str


class NautobotDeviceWithChildBay(NautobotModel):
    """A Device model with child OneToOne for testing the `NautobotModel` base class."""

    _model = dcim_models.Device
    _modelname = "device"
    _identifiers = ("name",)
    _children = {"device_bay": "parent_bay"}

    name: str
    parent_bay: List[NautobotDeviceBay] = []


class NautobotDeviceInvalidChildAttr(NautobotModel):
    """A Device model with invalid child attribute."""

    _model = dcim_models.Device
    _modelname = "device"
    _identifiers = ("name",)
    _children = {"device_bay": "invalid_attr"}

    name: str
    invalid_attr: List[NautobotDeviceBay] = []


class ContentTypeDict(TypedDict):
    """Many-to-many relationship typed dict explaining which fields are interesting."""

    app_label: str
    model: str


class TagModel(NautobotModel):
    """A model for testing the 'NautobotModel' class."""

    _model = extras_models.Tag
    _identifiers = ("name",)
    _attributes = ("content_types",)

    name: str
    content_types: List[ContentTypeDict] = []


class TestAdapter(NautobotAdapter):
    """An adapter for testing the `BaseAdapter` base class."""

    top_level = ("tenant_group",)
    tenant_group = NautobotTenantGroup
    tenant = NautobotTenant


class MockNautobotAdapter(NautobotAdapter):
    """Minimal adapter for unit-testing model CRUD without loading data.

    `top_level` is mocked so the adapter passes `validate_adapter()` without needing real models.
    """

    top_level = MagicMock()


class NautobotIPAddress(NautobotModel):
    """IP Address test model."""

    _model = ipam_models.IPAddress
    _modelname = "ip_address"
    _identifiers = (
        "host",
        "mask_length",
    )
    _attributes = (
        "status__name",
        "parent__network",
        "parent__prefix_length",
    )

    host: str
    mask_length: int
    status__name: str
    parent__network: str
    parent__prefix_length: str


class IPAddressDict(TypedDict):
    """Many-to-many relationship typed dict explaining which fields are interesting."""

    host: str
    mask_length: int


class NautobotInterface(NautobotModel):
    """Interface test model."""

    _model = dcim_models.Interface
    _modelname = "interface"
    _identifiers = (
        "name",
        "device__name",
    )
    _attributes = ("ip_addresses",)

    name: str
    device__name: str
    ip_addresses: List[IPAddressDict] = []


class NautobotDevice(NautobotModel):
    """Device test model."""

    _model = dcim_models.Device
    _modelname = "device"
    _identifiers = ("name",)
    _attributes = (
        "primary_ip4__host",
        "primary_ip4__mask_length",
        "role__name",
    )

    name: str
    role__name: str
    primary_ip4__host: Optional[str] = None
    primary_ip4__mask_length: Optional[int] = None


class NautobotCable(NautobotModel):
    """Model for cables between device interfaces.

    Note: This model doesn't support terminating to things other than device interfaces because of the way is is
    implemented.
    """

    _model = dcim_models.Cable
    _modelname = "cable"
    _identifiers = (
        "termination_a__name",
        "termination_a__device__name",
        "termination_b__name",
        "termination_b__device__name",
    )
    _attributes = (
        "termination_a__app_label",
        "termination_a__model",
        "termination_b__app_label",
        "termination_b__model",
    )

    termination_a__app_label: str
    termination_a__model: str
    termination_a__name: str
    termination_a__device__name: str

    termination_b__app_label: str
    termination_b__model: str
    termination_b__name: str
    termination_b__device__name: str


class TenantModelCustomRelationship(NautobotModel):
    """Tenant model for testing custom relationship support."""

    _model = tenancy_models.Tenant
    _modelname = "tenant"
    _identifiers = ("name",)
    _attributes = ("provider__name",)

    name: str
    provider__name: Annotated[
        Optional[str], CustomRelationshipAnnotation(name="Test Relationship", side=RelationshipSideEnum.DESTINATION)
    ] = None


class TenantDict(TypedDict):
    """Many-to-many relationship typed dict explaining which fields are interesting."""

    name: str


class ProviderModelCustomRelationship(NautobotModel):
    """Provider model for testing custom relationship support."""

    _model = circuits_models.Provider
    _modelname = "provider"
    _identifiers = ("name",)
    _attributes = ("tenants",)

    name: str
    tenants: Annotated[
        List[TenantDict], CustomRelationshipAnnotation(name="Test Relationship", side=RelationshipSideEnum.SOURCE)
    ] = []


class CustomRelationshipTypedDict(TypedDict):
    """Typed dictionary for testing custom many to many relationships."""

    name: str


class TenantModelCustomManyTomanyRelationship(NautobotModel):
    """Model for testing sorting custom relationships."""

    _model = tenancy_models.Tenant
    _modelname = "tenant"
    _identifiers = ("name",)
    _attributes = ("tenants",)

    name: str
    tenants: List[TenantDict] = []


class ProviderDict(TypedDict):
    """Typed dict describing the interesting fields of a related Provider."""

    name: str


class TenantToOneProviderModel(NautobotModel):
    """Tenant with a DESTINATION-side to-one custom-relationship `provider` field (one-to-many)."""

    _model = tenancy_models.Tenant
    _modelname = "tenant"
    _identifiers = ("name",)
    _attributes = ("provider",)

    name: str
    provider: Annotated[
        Optional[ProviderDict],
        CustomRelationshipAnnotation(name="Test Relationship", side=RelationshipSideEnum.DESTINATION),
    ] = None
