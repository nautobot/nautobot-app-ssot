"""Base classes for contrib testing."""

from typing import Optional, List

from nautobot.circuits import models as circuits_models
from nautobot.dcim import models as dcim_models
from nautobot.dcim.choices import InterfaceTypeChoices
from nautobot.extras import models as extras_models
from nautobot.ipam import models as ipam_models
from nautobot.tenancy import models as tenancy_models
from nautobot.utilities.testing import TestCase
from typing_extensions import TypedDict, Annotated

from nautobot_ssot.contrib import NautobotModel, NautobotAdapter, CustomRelationshipAnnotation, RelationshipSideEnum


class TestCaseWithDeviceData(TestCase):
    """Creates device data."""

    @classmethod
    def setUpTestData(cls):
        cls.status_active = extras_models.Status.objects.get(name="Active")
        cls.device_role = dcim_models.DeviceRole.objects.create(name="Switch")
        cls.manufacturer = dcim_models.Manufacturer.objects.create(name="Generic Inc.")
        cls.device_type = dcim_models.DeviceType.objects.create(model="Generic Switch", manufacturer=cls.manufacturer)
        cls.site = dcim_models.Site.objects.create(
            name="Bremen",
            status=cls.status_active,
        )
        for name in ["sw01", "sw02"]:
            device = dcim_models.Device.objects.create(
                status=cls.status_active,
                site=cls.site,
                name=name,
                device_role=cls.device_role,
                device_type=cls.device_type,
            )
            dcim_models.Interface.objects.create(
                device=device,
                name="Loopback 1",
                type=InterfaceTypeChoices.TYPE_VIRTUAL,
                status=cls.status_active,
            )
        cls.prefix = ipam_models.Prefix.objects.create(prefix="192.0.2.0/24", status=cls.status_active)
        cls.ip_address_1 = ipam_models.IPAddress(
            address="192.0.2.1/24",
            status=cls.status_active,
        )
        cls.ip_address_1.save()
        cls.ip_address_2 = ipam_models.IPAddress.objects.create(
            address="192.0.2.2/24",
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
    _attributes = ("description", "group__name", "tags")

    name: str
    description: Optional[str] = None
    group__name: Optional[str] = None
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
        "primary_ip4__prefix_length",
        "device_role__name",
    )

    name: str
    device_role__name: str
    primary_ip4__host: Optional[str] = None
    primary_ip4__prefix_length: Optional[int] = None


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


class TenantDict(TypedDict):
    """Many-to-many relationship typed dict explaining which fields are interesting."""

    name: str


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
