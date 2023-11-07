"""Test code for generic base adapters/models."""
from typing import Optional, List
from unittest import skip
from unittest.mock import MagicMock
from diffsync.exceptions import ObjectNotFound
from django.contrib.contenttypes.models import ContentType
from nautobot.circuits.models import Provider
from nautobot.dcim.choices import InterfaceTypeChoices
from nautobot.dcim.models import LocationType, Location, Manufacturer, DeviceType, Device, Interface
from nautobot.extras.choices import RelationshipTypeChoices
from nautobot.extras.models import Tag, Status, CustomField, Role, Relationship, RelationshipAssociation
from nautobot.ipam.models import Prefix, IPAddress, Namespace
from nautobot.tenancy.models import Tenant, TenantGroup
from nautobot.core.testing import TestCase
from typing_extensions import TypedDict, Annotated

from nautobot_ssot.contrib import (
    NautobotModel,
    NautobotAdapter,
    CustomFieldAnnotation,
    CustomRelationshipAnnotation,
    RelationshipSideEnum,
)


class TestCaseWithDeviceData(TestCase):
    """Creates device data."""

    @classmethod
    def setUpTestData(cls):
        cls.status_active = Status.objects.get(name="Active")
        cls.device_role = Role.objects.create(name="Switch")
        cls.manufacturer = Manufacturer.objects.create(name="Generic Inc.")
        cls.device_type = DeviceType.objects.create(model="Generic Switch", manufacturer=cls.manufacturer)
        cls.device_name = "sw01"
        cls.location = Location.objects.create(
            name="Bremen", location_type=LocationType.objects.get_or_create(name="Site")[0], status=cls.status_active
        )
        cls.device = Device.objects.create(
            status=cls.status_active,
            location=cls.location,
            name=cls.device_name,
            role=cls.device_role,
            device_type=cls.device_type,
        )
        cls.interface_name = "Loopback 1"
        cls.interface = Interface.objects.create(
            device=cls.device, name=cls.interface_name, type=InterfaceTypeChoices.TYPE_VIRTUAL, status=cls.status_active
        )
        cls.prefix = Prefix.objects.create(
            prefix="192.168.2.0/24", namespace=Namespace.objects.get(name="Global"), status=cls.status_active
        )
        super().setUpTestData()


class TagDict(TypedDict):
    """Many-to-many relationship typed dict explaining which fields are interesting."""

    name: str


class NautobotTenant(NautobotModel):
    """A tenant model for testing the `NautobotModel` base class."""

    _model = Tenant
    _modelname = "tenant"
    _identifiers = ("name",)
    _attributes = ("description", "tenant_group__name", "tags")

    name: str
    description: Optional[str] = None
    tenant_group__name: Optional[str] = None
    tags: List[TagDict] = []


class NautobotTenantGroup(NautobotModel):
    """A tenant group model for testing the `NautobotModel` base class."""

    _model = TenantGroup
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

    _model = Tag
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

    _model = IPAddress
    _modelname = "ip_address"
    _identifiers = (
        "host",
        "mask_length",
    )
    _attributes = ("status__name", "parent__prefix")

    host: str
    mask_length: int
    status__name: str
    parent__prefix: str


class IPAddressDict(TypedDict):
    """Many-to-many relationship typed dict explaining which fields are interesting."""

    host: str
    mask_length: int


class NautobotInterface(NautobotModel):
    """Interface test model."""

    _model = Interface
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

    _model = Device
    _modelname = "device"
    _identifiers = ("name",)
    _attributes = ("primary_ip4__host", "primary_ip4__mask_length")

    name: str
    primary_ip4__host: str
    primary_ip4__mask_length: int


class NautobotAdapterOneToOneRelationTests(TestCaseWithDeviceData):
    """Testing the one-to-one relation capability of the 'NautobotAdapter' class."""

    @skip("TODO: Update for 2.0")
    def test_one_to_one_relationship(self):
        """Test that loading a one-to-one relationship works."""

        class Adapter(NautobotAdapter):
            """Adapter for loading one-to-one relationship fields on a device."""

            top_level = ("device",)
            device = NautobotDevice

        ip_address = IPAddress.objects.create(host="192.0.2.1", mask_length=28, parent=self.prefix)
        self.interface.ip_addresses.add(ip_address)
        self.device.primary_ip4 = ip_address
        self.device.validated_save()

        adapter = Adapter(job=MagicMock())
        adapter.load()
        diffsync_device = adapter.get(NautobotDevice, {"name": self.device})

        self.assertEqual(ip_address.host, diffsync_device.primary_ip4__host)
        self.assertEqual(ip_address.mask_length, diffsync_device.primary_ip4__mask_length)


class NautobotAdapterGenericRelationTests(TestCaseWithDeviceData):
    """Testing the generic relation capability of the 'NautobotAdapter' class."""

    @skip("TODO: Update for 2.0")
    def test_load_generic_relationship_forwards(self):
        """Test that loading a generic relationship forwards works."""

        class Adapter(NautobotAdapter):
            """Adapter for loading generic relationship fields on an interface."""

            top_level = ("interface",)
            interface = NautobotInterface

        ip_address_1 = IPAddress.objects.create(host="192.0.2.1", mask_length=24)
        ip_address_2 = IPAddress.objects.create(host="192.0.2.2", mask_length=24)

        self.interface.ip_addresses.set([ip_address_1, ip_address_2])

        adapter = Adapter(job=MagicMock())
        adapter.load()
        diffsync_interface = adapter.get(
            NautobotInterface, {"name": self.interface_name, "device__name": self.device_name}
        )

        self.assertEqual(
            diffsync_interface.ip_addresses,
            [{"host": "192.0.2.1", "mask_length": 24}, {"host": "192.0.2.2", "mask_length": 24}],
        )

    @skip("TODO: Update for 2.0")
    def test_load_generic_relationship_backwards(self):
        """Test that loading a generic relationship backwards works."""

        class Adapter(NautobotAdapter):
            """Adapter for loading generic relationship fields on an IP address."""

            top_level = ("ip_address",)
            ip_address = NautobotIPAddress

        ip_address_1 = IPAddress.objects.create(
            host="192.0.2.1", mask_length=24, status=Status.objects.get(name="Active"), parent=self.prefix
        )

        self.interface.ip_addresses.set([ip_address_1])

        adapter = Adapter(job=MagicMock())
        adapter.load()
        diffsync_ip_address = adapter.get(NautobotIPAddress, {"host": "192.0.2.1", "mask_length": 24})

        # self.assertEqual(diffsync_ip_address.assigned_object__app_label, "dcim")
        # self.assertEqual(diffsync_ip_address.assigned_object__model, "interface")
        # self.assertEqual(diffsync_ip_address.assigned_object__device__name, self.device_name)
        # self.assertEqual(diffsync_ip_address.assigned_object__name, self.interface_name)
        self.assertEqual(diffsync_ip_address.parent__prefix, self.prefix.prefix)


class NautobotAdapterTests(TestCase):
    """Testing the 'NautobotAdapter' class."""

    @classmethod
    def setUpTestData(cls):
        cls.tenant_group_name = "Test Group"
        cls.tenant_group = TenantGroup.objects.create(name=cls.tenant_group_name, description="Test Group Description")
        cls.tenant_name = "Test"
        cls.tenant = Tenant.objects.create(name=cls.tenant_name, tenant_group=cls.tenant_group)
        cls.tags = [{"name": "space"}, {"name": "earth"}]
        for tag_dict in cls.tags:
            tag_object = Tag.objects.create(name=tag_dict["name"])
            tag_object.content_types.set([ContentType.objects.get_for_model(Tenant)])
            cls.tenant.tags.add(tag_object)

        cls.custom_field = CustomField.objects.create(key="Test", label="Test")
        cls.custom_field.content_types.set([ContentType.objects.get_for_model(Provider)])

    def test_basic_loading(self):
        adapter = TestAdapter(job=MagicMock())
        adapter.load()
        try:
            adapter.get(NautobotTenantGroup, self.tenant_group_name)
        except ObjectNotFound:
            self.fail("Generic Nautobot adapter not loading top level objects correctly.")

    def test_children(self):
        adapter = TestAdapter(job=MagicMock())
        adapter.load()
        try:
            adapter.get(NautobotTenant, self.tenant_name)
        except ObjectNotFound:
            self.fail("Generic Nautobot adapter not loading child level objects correctly.")

    def test_load_custom_fields(self):
        class ProviderModel(NautobotModel):
            """Test model with a custom field,"""

            _model = Provider
            _modelname = "provider"
            _identifiers = ("name",)
            _attributes = ("custom_field",)

            name: str
            custom_field: Annotated[str, CustomFieldAnnotation(name="Test")]

        class Adapter(NautobotAdapter):
            """Test adapter including a model with a custom field."""

            top_level = ("provider",)
            provider = ProviderModel

        custom_field_value = "Custom Field Value"
        provider_name = "Test"
        Provider.objects.create(name=provider_name, _custom_field_data={"Test": custom_field_value})

        adapter = Adapter(job=MagicMock())
        adapter.load()
        diffsync_provider = adapter.get(ProviderModel, provider_name)

        self.assertEqual(
            custom_field_value,
            diffsync_provider.custom_field,
            "Custom fields aren't properly loaded through 'BaseAdapter'.",
        )

    def test_overwrite_get_queryset(self):
        """Test overriding 'get_queryset' method."""

        class TenantModel(NautobotModel):
            """Test model for testing overridden 'get_queryset' method."""

            _model = Tenant
            _modelname = "tenant"
            _identifiers = ("name",)
            _attributes = ("description",)

            name: str
            description: str

            @classmethod
            def get_queryset(cls):
                return Tenant.objects.filter(name__startswith="N")

        class Adapter(NautobotAdapter):
            """Test overriding 'get_queryset' method."""

            top_level = ("tenant",)
            tenant = TenantModel

        new_tenant_name = "NASA"
        Tenant.objects.create(name=new_tenant_name)
        Tenant.objects.create(name="Air Force")
        adapter = Adapter(job=MagicMock())
        adapter.load()
        diffsync_tenant = adapter.get(TenantModel, new_tenant_name)

        self.assertEqual(new_tenant_name, diffsync_tenant.name)


class BaseModelTests(TestCase):
    """Testing basic operations through 'NautobotModel'."""

    tenant_name = "Test Tenant"
    tenant_group_name = "Test Tenant Group"

    def test_basic_creation(self):
        """Test whether a basic create of an object works."""
        NautobotTenant.create(diffsync=None, ids={"name": self.tenant_name}, attrs={})
        try:
            Tenant.objects.get(name=self.tenant_name)
        except Tenant.DoesNotExist:
            self.fail("Basic object creation through 'NautobotModel' does not work.")

    def test_basic_update(self):
        """Test whether a basic update of an object works."""
        tenant = Tenant.objects.create(name=self.tenant_name)
        description = "An updated description"
        diffsync_tenant = NautobotTenant(name=self.tenant_name)
        diffsync_tenant.update(attrs={"description": description})
        tenant.refresh_from_db()
        self.assertEqual(
            tenant.description, description, "Basic object updating through 'NautobotModel' does not work."
        )

    def test_basic_deletion(self):
        """Test whether basic deletion of an object works."""
        Tenant.objects.create(name=self.tenant_name)

        diffsync_tenant = NautobotTenant(name=self.tenant_name)
        diffsync_tenant.delete()

        try:
            Tenant.objects.get(name=self.tenant_name)
            self.fail("Basic object deletion through 'NautobotModel' does not work.")
        except Tenant.DoesNotExist:
            pass


class BaseModelCustomFieldTest(TestCase):
    """Test for manipulating custom field content through the shared case model code."""

    def test_custom_field_set(self):
        """Test whether setting a custom field value works."""
        custom_field_name = "Is Global"
        custom_field = CustomField.objects.create(key="is_global", label=custom_field_name, type="boolean")
        custom_field.content_types.set([ContentType.objects.get_for_model(Provider)])

        class ProviderModel(NautobotModel):
            """Test model for testing custom field functionality."""

            _model = Provider
            _identifiers = ("name",)
            _attributes = ("is_global",)

            name: str

            is_global: Annotated[bool, CustomFieldAnnotation(name="is_global")] = False

        provider_name = "Test Provider"
        provider = Provider.objects.create(name=provider_name)

        diffsync_provider = ProviderModel(name=provider_name)
        updated_custom_field_value = True
        diffsync_provider.update(attrs={"is_global": updated_custom_field_value})

        provider.refresh_from_db()
        self.assertEqual(
            provider.cf["is_global"],
            updated_custom_field_value,
            "Setting a custom field through 'NautobotModel' does not work.",
        )


class BaseModelForeignKeyTest(TestCase):
    """Tests for manipulating foreign key relationships through the shared base model code."""

    tenant_name = "Test Tenant"
    tenant_group_name = "Test Tenant Group"

    def test_foreign_key_add(self):
        """Test whether setting a foreign key works."""
        group = TenantGroup.objects.create(name=self.tenant_group_name)
        tenant = Tenant.objects.create(name=self.tenant_name)

        diffsync_tenant = NautobotTenant(name=self.tenant_name)
        diffsync_tenant.update(attrs={"tenant_group__name": self.tenant_group_name})

        tenant.refresh_from_db()
        self.assertEqual(
            group, tenant.tenant_group, "Foreign key update from None through 'NautobotModel' does not work."
        )

    def test_foreign_key_remove(self):
        """Test whether unsetting a foreign key works."""
        group = TenantGroup.objects.create(name=self.tenant_group_name)
        tenant = Tenant.objects.create(name=self.tenant_name, tenant_group=group)

        diffsync_tenant = NautobotTenant(name=self.tenant_name, tenant_group__name=self.tenant_group_name)
        diffsync_tenant.update(attrs={"tenant_group__name": None})

        tenant.refresh_from_db()
        self.assertEqual(None, tenant.tenant_group, "Foreign key update to None through 'NautobotModel' does not work.")

    def test_foreign_key_add_multiple_fields(self):
        """Test whether setting a foreign key using multiple fields works."""
        location_type_a = LocationType.objects.create(name="Room")
        location_type_b = LocationType.objects.create(name="Building")
        location_type_a.content_types.set([ContentType.objects.get_for_model(Prefix)])
        location_type_b.content_types.set([ContentType.objects.get_for_model(Prefix)])
        location_a = Location.objects.create(
            name="Room A", location_type=location_type_a, status=Status.objects.get(name="Active")
        )
        location_b = Location.objects.create(
            name="Room B", location_type=location_type_b, status=Status.objects.get(name="Active")
        )

        class PrefixModel(NautobotModel):
            """Test model for testing foreign key functionality."""

            _model = Prefix
            _identifiers = ("network", "prefix_length")
            _attributes = ("location__name", "location__location_type__name")

            network: str
            prefix_length: int

            location__name: str
            location__location_type__name: str

        network = "192.0.2.0"
        prefix_length = 24
        prefix = Prefix.objects.create(
            network=network, prefix_length=prefix_length, location=location_a, status=Status.objects.get(name="Active")
        )
        prefix_diffsync = PrefixModel(
            network=network,
            prefix_length=prefix_length,
            location__name=location_a.name,
            location__location_type__name=location_a.location_type.name,
        )

        prefix_diffsync.update(
            attrs={"location__name": location_b.name, "location__location_type__name": location_b.location_type.name}
        )
        prefix.refresh_from_db()

        self.assertEqual(prefix.location, location_b)


class BaseModelGenericRelationTest(TestCaseWithDeviceData):
    """Test for manipulating generic relations through the shared base model code."""

    @skip("Needs to be updated for 2.0")
    def test_generic_relation_add_forwards(self):
        ip_address_1 = IPAddress.objects.create(host="192.0.2.1", mask_length=24, parent=self.prefix)
        ip_address_2 = IPAddress.objects.create(host="192.0.2.2", mask_length=24, parent=self.prefix)

        diffsync_interface = NautobotInterface(
            name=self.interface_name,
            device__name=self.device_name,
            type=InterfaceTypeChoices.TYPE_VIRTUAL,
        )
        diffsync_interface.update(
            attrs={
                "ip_addresses": [
                    {"host": ip_address_1.host, "mask_length": ip_address_1.mask_length},
                    {"host": ip_address_2.host, "mask_length": ip_address_2.mask_length},
                ],
            }
        )

        self.assertEqual(list(self.interface.ip_addresses.all()), [ip_address_1, ip_address_2])

    @skip("TODO: Update for 2.0")
    def test_generic_relation_add_backwards(self):
        diffsync_ip_address = NautobotIPAddress.create(
            diffsync=None,
            ids={"host": "192.0.2.1", "mask_length": 24},
            attrs={
                "status__name": "Active",
                "parent__prefix": "192.0.2.0/24",
            },
        )
        # The 'get_from_db' function comes from NautobotModel, I don't see why this pylint warning occurs.
        nautobot_ip_address = diffsync_ip_address.get_from_db()  # pylint: disable=no-member
        self.assertEqual(self.prefix, nautobot_ip_address.parent)


class TenantModelCustomRelationship(NautobotModel):
    """Tenant model for testing custom relationship support."""

    _model = Tenant
    _modelname = "tenant"
    _identifiers = ("name",)
    _attributes = ("provider__name",)

    name: str
    provider__name: Annotated[
        Optional[str], CustomRelationshipAnnotation(name="Test Relationship", side=RelationshipSideEnum.SOURCE)
    ] = None


class TenantDict(TypedDict):
    """Many-to-many relationship typed dict explaining which fields are interesting."""

    name: str


class ProviderModelCustomRelationship(NautobotModel):
    """Provider model for testing custom relationship support."""

    _model = Provider
    _modelname = "provider"
    _identifiers = ("name",)
    _attributes = ("tenants",)

    name: str
    tenants: Annotated[
        List[TenantDict], CustomRelationshipAnnotation(name="Test Relationship", side=RelationshipSideEnum.DESTINATION)
    ] = []


class CustomRelationShipTestAdapterSource(NautobotAdapter):
    """Adapter for testing custom relationship support."""

    top_level = ["tenant"]
    tenant = TenantModelCustomRelationship


class CustomRelationShipTestAdapterDestination(NautobotAdapter):
    """Adapter for testing custom relationship support."""

    top_level = ["provider"]
    provider = ProviderModelCustomRelationship


class AdapterCustomRelationshipTest(TestCase):
    """Test case for custom relationships."""

    def setUp(self):
        self.relationship = Relationship.objects.create(
            label="Test Relationship",
            source_type=ContentType.objects.get_for_model(Tenant),
            destination_type=ContentType.objects.get_for_model(Provider),
            type=RelationshipTypeChoices.TYPE_ONE_TO_MANY,
        )
        self.tenant = Tenant.objects.create(name="Test Tenant")
        self.provider = Provider.objects.create(name="Test Provider")
        RelationshipAssociation.objects.create(
            relationship=self.relationship,
            source=self.tenant,
            destination=self.provider,
        )

    def test_load_source(self):
        """Test loading a single custom relationship from the source side."""
        adapter = CustomRelationShipTestAdapterSource(job=MagicMock())
        adapter.load()
        self.assertEqual(adapter.get_all("tenant")[0].provider__name, self.provider.name)

    def test_load_destination(self):
        """Test loading a single custom relationship from the destination side."""
        adapter = CustomRelationShipTestAdapterDestination(job=MagicMock())
        adapter.load()
        message = "Loading custom relationships through the destination side doesn't work."
        try:
            diffsync_provider = adapter.get_all("provider")[0]
            tenant_name = diffsync_provider.tenants[0]["name"]
        except IndexError:
            self.fail(message)
        self.assertEqual(tenant_name, self.tenant.name, msg=message)


class BaseModelCustomRelationshipTest(TestCase):
    """Tests for manipulating custom relationships through the shared base model code."""

    @classmethod
    def setUpTestData(cls):
        cls.relationship = Relationship.objects.create(
            label="Test Relationship",
            source_type=ContentType.objects.get_for_model(Tenant),
            destination_type=ContentType.objects.get_for_model(Provider),
        )
        cls.tenant_one = Tenant.objects.create(name="Test Tenant 1")
        cls.tenant_two = Tenant.objects.create(name="Test Tenant 2")
        cls.provider_one = Provider.objects.create(name="Test Provider 1")
        cls.provider_two = Provider.objects.create(name="Test Provider 2")

    def test_custom_relationship_add_foreign_key(self):
        diffsync_tenant = TenantModelCustomRelationship(
            name=self.tenant_one.name,
        )
        diffsync_tenant.diffsync = CustomRelationShipTestAdapterSource(job=MagicMock())
        diffsync_tenant.update({"provider__name": self.provider_one.name})
        self.assertEqual(RelationshipAssociation.objects.count(), 1)

    def test_custom_relationship_update_foreign_key(self):
        diffsync_tenant = TenantModelCustomRelationship(
            name=self.tenant_one.name,
        )
        diffsync_tenant.diffsync = CustomRelationShipTestAdapterSource(job=MagicMock())
        diffsync_tenant.update({"provider__name": self.provider_one.name})
        diffsync_tenant.update({"provider__name": self.provider_two.name})
        self.assertEqual(RelationshipAssociation.objects.first().destination, self.provider_two)

    def test_custom_relationship_add_to_many(self):
        diffsync_provider = ProviderModelCustomRelationship(
            name=self.provider_one.name,
        )
        diffsync_provider.diffsync = CustomRelationShipTestAdapterDestination(job=MagicMock())
        diffsync_provider.update({"tenants": [{"name": self.tenant_one.name}, {"name": self.tenant_two.name}]})
        self.assertEqual(RelationshipAssociation.objects.count(), 2)

    def test_custom_relationship_update_to_many(self):
        diffsync_provider = ProviderModelCustomRelationship(
            name=self.provider_one.name,
        )
        diffsync_provider.diffsync = CustomRelationShipTestAdapterDestination(job=MagicMock())
        diffsync_provider.update({"tenants": [{"name": self.tenant_one.name}]})
        diffsync_provider.update({"tenants": [{"name": self.tenant_two.name}]})
        self.assertEqual(RelationshipAssociation.objects.count(), 1)
        self.assertEqual(RelationshipAssociation.objects.first().source, self.tenant_two)


class BaseModelManyToManyTest(TestCase):
    """Tests for manipulating many-to-many relationships through the shared base model code."""

    tag_names = ["cool-tenant", "hip-tenant"]
    tenant_name = "Test Tenant"

    @classmethod
    def setUpTestData(cls):
        cls.tags = [Tag.objects.create(name=tag_name) for tag_name in cls.tag_names]

    def test_many_to_many_add(self):
        """Test whether adding to a many-to-many relationship works."""
        tenant = Tenant.objects.create(name=self.tenant_name)
        tenant.tags.add(self.tags[0])

        diffsync_tenant = NautobotTenant(name=self.tenant_name, tags=[{"name": self.tags[0].name}])
        diffsync_tenant.update(attrs={"tags": [{"name": tag.name} for tag in self.tags]})

        tenant.refresh_from_db()
        self.assertEqual(
            list(tenant.tags.values_list("name", flat=True)),
            self.tag_names,
            "Adding an object to a many-to-many relationship through 'NautobotModel' does not work.",
        )

    def test_many_to_many_remove(self):
        """Test whether removing a single object from a many-to-many relationship works."""
        tenant = Tenant.objects.create(name=self.tenant_name)
        tenant.tags.set(self.tags)

        diffsync_tenant = NautobotTenant(name=self.tenant_name, tags=[{"name": tag.name} for tag in self.tags])
        diffsync_tenant.update(attrs={"tags": [{"name": self.tags[0].name}]})

        tenant.refresh_from_db()
        self.assertEqual(
            list(tenant.tags.values_list("name", flat=True)),
            [self.tags[0].name],
            "Removing an object from a many-to-many relationship through 'NautobotModel' does not work.",
        )

    def test_many_to_many_null(self):
        """Test whether removing all elements from a many-to-many relationship works."""
        tenant = Tenant.objects.create(name=self.tenant_name)
        tenant.tags.set(self.tags)

        diffsync_tenant = NautobotTenant(name=self.tenant_name, tags=[{"name": tag.name} for tag in self.tags])
        diffsync_tenant.update(attrs={"tags": []})

        tenant.refresh_from_db()
        self.assertEqual(
            list(tenant.tags.values_list("name", flat=True)),
            [],
            "Nulling a many-to-many relationship through 'NautobotModel' does not work.",
        )

    def test_many_to_many_multiple_fields_add(self):
        """Test whether adding items to a many-to-many relationship using multiple fields works."""
        name = "Test Tag"
        tag = Tag.objects.create(name=name)

        content_types = [{"app_label": "dcim", "model": "device"}, {"app_label": "circuits", "model": "provider"}]
        tag_diffsync = TagModel(name=name)
        tag_diffsync.update(attrs={"content_types": content_types})

        tag.refresh_from_db()
        self.assertEqual(
            list(tag.content_types.values("app_label", "model")),
            content_types,
            "Adding objects to a many-to-many relationship based on more than one parameter through 'NautobotModel'"
            "does not work.",
        )

    def test_many_to_many_multiple_fields_remove(self):
        """Test whether removing items from a many-to-many relationship using multiple fields works."""
        name = "Test Tag"
        tag = Tag.objects.create(name=name)
        content_types = [{"app_label": "dcim", "model": "device"}, {"app_label": "circuits", "model": "provider"}]
        tag.content_types.set([ContentType.objects.get(**parameters) for parameters in content_types])

        tag_diffsync = TagModel(name=name)
        tag_diffsync.update(attrs={"content_types": []})

        tag.refresh_from_db()
        self.assertEqual(
            list(tag.content_types.values("app_label", "model")),
            [],
            "Removing objects to a many-to-many relationship based on more than one parameter through 'NautobotModel'"
            "does not work.",
        )
