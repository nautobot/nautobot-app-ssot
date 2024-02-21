"""Test code for generic base adapters/models."""
from typing import Optional, List
from unittest import skip
from unittest.mock import MagicMock
from diffsync.exceptions import ObjectNotFound
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.db import connection
from django.test.utils import CaptureQueriesContext
import nautobot.circuits.models as circuits_models
from nautobot.dcim.choices import InterfaceTypeChoices
from nautobot.extras.choices import RelationshipTypeChoices
import nautobot.extras.models as extras_models
import nautobot.dcim.models as dcim_models
import nautobot.ipam.models as ipam_models
import nautobot.tenancy.models as tenancy_models
from nautobot.utilities.testing import TestCase
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


class NautobotAdapterOneToOneRelationTests(TestCaseWithDeviceData):
    """Testing the one-to-one relation capability of the 'NautobotAdapter' class."""

    def test_one_to_one_relationship(self):
        """Test that loading a one-to-one relationship works."""

        class Adapter(NautobotAdapter):
            """Adapter for loading one-to-one relationship fields on a device."""

            top_level = ("device",)
            device = NautobotDevice

        device = dcim_models.Device.objects.first()
        interface = dcim_models.Interface.objects.get(name="Loopback 1", device=device)
        interface.ip_addresses.add(self.ip_address_1)
        device.primary_ip4 = self.ip_address_1
        device.validated_save()

        adapter = Adapter(job=MagicMock())
        adapter.load()
        diffsync_device = adapter.get(NautobotDevice, {"name": device.name})

        self.assertEqual(self.ip_address_1.host, diffsync_device.primary_ip4__host)
        self.assertEqual(self.ip_address_1.prefix_length, diffsync_device.primary_ip4__prefix_length)


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


class NautobotAdapterGenericRelationTests(TestCaseWithDeviceData):
    """Testing the generic relation capability of the 'NautobotAdapter' class."""

    def setUp(self):
        dcim_models.Cable.objects.create(
            termination_a=dcim_models.Interface.objects.all().filter(name="Loopback 1").first(),
            termination_b=dcim_models.Interface.objects.all().filter(name="Loopback 1").last(),
            status=extras_models.Status.objects.get(name="Active"),
        )
        super().setUp()

    def test_load_generic_relationship_forwards(self):
        """Test that loading a generic relationship forwards works."""

        class Adapter(NautobotAdapter):
            """Adapter for loading generic relationship fields on an interface."""

            top_level = ("cable",)
            cable = NautobotCable

        adapter = Adapter(job=MagicMock())
        adapter.load()
        try:
            diffsync_cable = adapter.get_all("cable")[0]
        except IndexError:
            self.fail("Cable with generic relationships wasn't properly loaded by adapter.")

        expected = {
            "termination_a__app_label": "dcim",
            "termination_a__model": "interface",
            "termination_a__name": "Loopback 1",
            "termination_a__device__name": "sw01",
            "termination_b__app_label": "dcim",
            "termination_b__model": "interface",
            "termination_b__name": "Loopback 1",
            "termination_b__device__name": "sw02",
        }
        for key, value in expected.items():
            self.assertEqual(getattr(diffsync_cable, key), value, "Generic foreign key wasn't loaded correctly.")

    @skip("See docstring")
    def test_load_generic_relationship_backwards(self):
        """Skipped.

        As of Nautobot 2, there is no model in Nautobot core with a generic relationship that has 'related_name' set
        (as cable terminations don't provide a backwards relation). Thus, this test will be skipped for now.
        """


class NautobotAdapterTests(TestCase):
    """Testing the 'NautobotAdapter' class."""

    @classmethod
    def setUpTestData(cls):
        cls.tenant_group_name = "Test Group"
        cls.tenant_group = tenancy_models.TenantGroup.objects.create(
            name=cls.tenant_group_name, description="Test Group Description"
        )
        cls.tenant_name = "Test"
        cls.tenant = tenancy_models.Tenant.objects.create(name=cls.tenant_name, group=cls.tenant_group)
        cls.tags = [{"name": "space"}, {"name": "earth"}]
        for tag_dict in cls.tags:
            tag_object = extras_models.Tag.objects.create(name=tag_dict["name"])
            tag_object.content_types.set([ContentType.objects.get_for_model(tenancy_models.Tenant)])
            cls.tenant.tags.add(tag_object)

        cls.custom_field = extras_models.CustomField.objects.create(name="Test", label="Test")
        cls.custom_field.content_types.set([ContentType.objects.get_for_model(circuits_models.Provider)])

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

            _model = circuits_models.Provider
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
        circuits_models.Provider.objects.create(name=provider_name, _custom_field_data={"Test": custom_field_value})

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

            _model = tenancy_models.Tenant
            _modelname = "tenant"
            _identifiers = ("name",)
            _attributes = ("description",)

            name: str
            description: str

            @classmethod
            def get_queryset(cls):
                return tenancy_models.Tenant.objects.filter(name__startswith="N")

        class Adapter(NautobotAdapter):
            """Test overriding 'get_queryset' method."""

            top_level = ("tenant",)
            tenant = TenantModel

        new_tenant_name = "NASA"
        tenancy_models.Tenant.objects.create(name=new_tenant_name)
        tenancy_models.Tenant.objects.create(name="Air Force")
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
            tenancy_models.Tenant.objects.get(name=self.tenant_name)
        except tenancy_models.Tenant.DoesNotExist:
            self.fail("Basic object creation through 'NautobotModel' does not work.")

    def test_basic_update(self):
        """Test whether a basic update of an object works."""
        tenant = tenancy_models.Tenant.objects.create(name=self.tenant_name)
        description = "An updated description"
        diffsync_tenant = NautobotTenant(name=self.tenant_name)
        diffsync_tenant.diffsync = NautobotAdapter(job=None, sync=None)
        diffsync_tenant.update(attrs={"description": description})
        tenant.refresh_from_db()
        self.assertEqual(
            tenant.description, description, "Basic object updating through 'NautobotModel' does not work."
        )

    def test_basic_deletion(self):
        """Test whether basic deletion of an object works."""
        tenancy_models.Tenant.objects.create(name=self.tenant_name)

        diffsync_tenant = NautobotTenant(name=self.tenant_name)
        diffsync_tenant.diffsync = NautobotAdapter(job=None, sync=None)
        diffsync_tenant.delete()

        try:
            tenancy_models.Tenant.objects.get(name=self.tenant_name)
            self.fail("Basic object deletion through 'NautobotModel' does not work.")
        except tenancy_models.Tenant.DoesNotExist:
            pass


class BaseModelCustomFieldTest(TestCase):
    """Test for manipulating custom field content through the shared case model code."""

    def test_custom_field_set(self):
        """Test whether setting a custom field value works."""
        custom_field_name = "Is Global"
        custom_field = extras_models.CustomField.objects.create(
            name="is_global", label=custom_field_name, type="boolean"
        )
        custom_field.content_types.set([ContentType.objects.get_for_model(circuits_models.Provider)])

        class ProviderModel(NautobotModel):
            """Test model for testing custom field functionality."""

            _model = circuits_models.Provider
            _identifiers = ("name",)
            _attributes = ("is_global",)

            name: str

            is_global: Annotated[bool, CustomFieldAnnotation(name="is_global")] = False

        provider_name = "Test Provider"
        provider = circuits_models.Provider.objects.create(name=provider_name)

        diffsync_provider = ProviderModel(name=provider_name)
        updated_custom_field_value = True
        diffsync_provider.diffsync = NautobotAdapter(job=None, sync=None)
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
        group = tenancy_models.TenantGroup.objects.create(name=self.tenant_group_name)
        tenant = tenancy_models.Tenant.objects.create(name=self.tenant_name)

        diffsync_tenant = NautobotTenant(name=self.tenant_name)
        diffsync_tenant.diffsync = NautobotAdapter(job=None, sync=None)
        diffsync_tenant.update(attrs={"group__name": self.tenant_group_name})

        tenant.refresh_from_db()
        self.assertEqual(group, tenant.group, "Foreign key update from None through 'NautobotModel' does not work.")

    def test_foreign_key_remove(self):
        """Test whether unsetting a foreign key works."""
        group = tenancy_models.TenantGroup.objects.create(name=self.tenant_group_name)
        tenant = tenancy_models.Tenant.objects.create(name=self.tenant_name, group=group)

        diffsync_tenant = NautobotTenant(name=self.tenant_name, group__name=self.tenant_group_name)
        diffsync_tenant.diffsync = NautobotAdapter(job=None, sync=None)
        diffsync_tenant.update(attrs={"group__name": None})

        tenant.refresh_from_db()
        self.assertEqual(None, tenant.group, "Foreign key update to None through 'NautobotModel' does not work.")

    def test_foreign_key_add_multiple_fields(self):
        """Test whether setting a foreign key using multiple fields works."""
        location_type_a = dcim_models.LocationType.objects.create(name="Room")
        location_type_b = dcim_models.LocationType.objects.create(name="Building")
        location_type_a.content_types.set([ContentType.objects.get_for_model(ipam_models.Prefix)])
        location_type_b.content_types.set([ContentType.objects.get_for_model(ipam_models.Prefix)])
        location_a = dcim_models.Location.objects.create(
            name="Room A", location_type=location_type_a, status=extras_models.Status.objects.get(name="Active")
        )
        location_b = dcim_models.Location.objects.create(
            name="Room B", location_type=location_type_b, status=extras_models.Status.objects.get(name="Active")
        )

        class PrefixModel(NautobotModel):
            """Test model for testing foreign key functionality."""

            _model = ipam_models.Prefix
            _identifiers = ("network", "prefix_length")
            _attributes = ("location__name", "location__location_type__name")

            network: str
            prefix_length: int

            location__name: str
            location__location_type__name: str

        network = "192.0.2.0"
        prefix_length = 24
        prefix = ipam_models.Prefix.objects.create(
            network=network,
            prefix_length=prefix_length,
            location=location_a,
            status=extras_models.Status.objects.get(name="Active"),
        )
        prefix_diffsync = PrefixModel(
            network=network,
            prefix_length=prefix_length,
            location__name=location_a.name,
            location__location_type__name=location_a.location_type.name,
        )
        prefix_diffsync.diffsync = NautobotAdapter(job=None, sync=None)

        prefix_diffsync.update(
            attrs={"location__name": location_b.name, "location__location_type__name": location_b.location_type.name}
        )
        prefix.refresh_from_db()

        self.assertEqual(prefix.location, location_b)


@skip("See docstrings.")
class BaseModelGenericRelationTest(TestCaseWithDeviceData):
    """Test for manipulating generic relations through the shared base model code."""

    def test_generic_relation_add_forwards(self):
        """Skipped.

        As of Nautobot 2, there is no model in Nautobot core with a generic relationship that makes sense to update as
        cables can't be updated due to their model validation enforcing this.
        """

    def test_generic_relation_add_backwards(self):
        """Skipped.

        As of Nautobot 2, there is no model in Nautobot core with a generic relationship that has 'related_name' set
        (as cable terminations don't provide a backwards relation). Thus, this test will be skipped for now.
        """


class TenantModelCustomRelationship(NautobotModel):
    """Tenant model for testing custom relationship support."""

    _model = tenancy_models.Tenant
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

    _model = circuits_models.Provider
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
        self.relationship = extras_models.Relationship.objects.create(
            name="Test Relationship",
            source_type=ContentType.objects.get_for_model(tenancy_models.Tenant),
            destination_type=ContentType.objects.get_for_model(circuits_models.Provider),
            type=RelationshipTypeChoices.TYPE_ONE_TO_MANY,
        )
        self.tenant = tenancy_models.Tenant.objects.create(name="Test Tenant")
        self.provider = circuits_models.Provider.objects.create(name="Test Provider")
        extras_models.RelationshipAssociation.objects.create(
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
        cls.relationship = extras_models.Relationship.objects.create(
            name="Test Relationship",
            source_type=ContentType.objects.get_for_model(tenancy_models.Tenant),
            destination_type=ContentType.objects.get_for_model(circuits_models.Provider),
        )
        cls.tenant_one = tenancy_models.Tenant.objects.create(name="Test Tenant 1")
        cls.tenant_two = tenancy_models.Tenant.objects.create(name="Test Tenant 2")
        cls.provider_one = circuits_models.Provider.objects.create(name="Test Provider 1")
        cls.provider_two = circuits_models.Provider.objects.create(name="Test Provider 2")

    def test_custom_relationship_add_foreign_key(self):
        diffsync_tenant = TenantModelCustomRelationship(
            name=self.tenant_one.name,
        )
        diffsync_tenant.diffsync = CustomRelationShipTestAdapterSource(job=MagicMock())
        diffsync_tenant.update({"provider__name": self.provider_one.name})
        self.assertEqual(extras_models.RelationshipAssociation.objects.count(), 1)

    def test_custom_relationship_update_foreign_key(self):
        diffsync_tenant = TenantModelCustomRelationship(
            name=self.tenant_one.name,
        )
        diffsync_tenant.diffsync = CustomRelationShipTestAdapterSource(job=MagicMock())
        diffsync_tenant.update({"provider__name": self.provider_one.name})
        diffsync_tenant.update({"provider__name": self.provider_two.name})
        self.assertEqual(extras_models.RelationshipAssociation.objects.first().destination, self.provider_two)

    def test_custom_relationship_add_to_many(self):
        diffsync_provider = ProviderModelCustomRelationship(
            name=self.provider_one.name,
        )
        diffsync_provider.diffsync = CustomRelationShipTestAdapterDestination(job=MagicMock())
        diffsync_provider.update({"tenants": [{"name": self.tenant_one.name}, {"name": self.tenant_two.name}]})
        self.assertEqual(extras_models.RelationshipAssociation.objects.count(), 2)

    def test_custom_relationship_update_to_many(self):
        diffsync_provider = ProviderModelCustomRelationship(
            name=self.provider_one.name,
        )
        diffsync_provider.diffsync = CustomRelationShipTestAdapterDestination(job=MagicMock())
        diffsync_provider.update({"tenants": [{"name": self.tenant_one.name}]})
        diffsync_provider.update({"tenants": [{"name": self.tenant_two.name}]})
        self.assertEqual(extras_models.RelationshipAssociation.objects.count(), 1)
        self.assertEqual(extras_models.RelationshipAssociation.objects.first().source, self.tenant_two)


class BaseModelManyToManyTest(TestCase):
    """Tests for manipulating many-to-many relationships through the shared base model code."""

    tag_names = ["cool-tenant", "hip-tenant"]
    tenant_name = "Test Tenant"

    @classmethod
    def setUpTestData(cls):
        cls.tags = [extras_models.Tag.objects.create(name=tag_name) for tag_name in cls.tag_names]

    def test_many_to_many_add(self):
        """Test whether adding to a many-to-many relationship works."""
        tenant = tenancy_models.Tenant.objects.create(name=self.tenant_name)
        tenant.tags.add(self.tags[0])

        diffsync_tenant = NautobotTenant(name=self.tenant_name, tags=[{"name": self.tags[0].name}])
        diffsync_tenant.diffsync = NautobotAdapter(job=None, sync=None)
        diffsync_tenant.update(attrs={"tags": [{"name": tag.name} for tag in self.tags]})

        tenant.refresh_from_db()
        self.assertEqual(
            list(tenant.tags.values_list("name", flat=True)),
            self.tag_names,
            "Adding an object to a many-to-many relationship through 'NautobotModel' does not work.",
        )

    def test_many_to_many_remove(self):
        """Test whether removing a single object from a many-to-many relationship works."""
        tenant = tenancy_models.Tenant.objects.create(name=self.tenant_name)
        tenant.tags.set(self.tags)

        diffsync_tenant = NautobotTenant(name=self.tenant_name, tags=[{"name": tag.name} for tag in self.tags])
        diffsync_tenant.diffsync = NautobotAdapter(job=None, sync=None)
        diffsync_tenant.update(attrs={"tags": [{"name": self.tags[0].name}]})

        tenant.refresh_from_db()
        self.assertEqual(
            list(tenant.tags.values_list("name", flat=True)),
            [self.tags[0].name],
            "Removing an object from a many-to-many relationship through 'NautobotModel' does not work.",
        )

    def test_many_to_many_null(self):
        """Test whether removing all elements from a many-to-many relationship works."""
        tenant = tenancy_models.Tenant.objects.create(name=self.tenant_name)
        tenant.tags.set(self.tags)

        diffsync_tenant = NautobotTenant(name=self.tenant_name, tags=[{"name": tag.name} for tag in self.tags])
        diffsync_tenant.diffsync = NautobotAdapter(job=None, sync=None)
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
        tag = extras_models.Tag.objects.create(name=name)

        content_types = [{"app_label": "dcim", "model": "device"}, {"app_label": "circuits", "model": "provider"}]
        tag_diffsync = TagModel(name=name)
        tag_diffsync.diffsync = NautobotAdapter(job=None, sync=None)
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
        tag = extras_models.Tag.objects.create(name=name)
        content_types = [{"app_label": "dcim", "model": "device"}, {"app_label": "circuits", "model": "provider"}]
        tag.content_types.set([ContentType.objects.get(**parameters) for parameters in content_types])

        tag_diffsync = TagModel(name=name)
        tag_diffsync.diffsync = NautobotAdapter(job=None, sync=None)
        tag_diffsync.update(attrs={"content_types": []})

        tag.refresh_from_db()
        self.assertEqual(
            list(tag.content_types.values("app_label", "model")),
            [],
            "Removing objects to a many-to-many relationship based on more than one parameter through 'NautobotModel'"
            "does not work.",
        )


class CacheTests(TestCase):
    """Tests caching functionality between the nautobot adapter and model base classes."""

    def test_caching(self):
        """Test the cache mechanism built into the Nautobot adapter."""
        # Postgres uses '"' while MySQL uses '`'
        backend = settings.DATABASES["default"]["ENGINE"]
        *_, suffix = backend.split(".")
        if suffix == "postgresql":
            query_filter = 'FROM "tenancy_tenantgroup"'
        elif suffix == "mysql":
            query_filter = "FROM `tenancy_tenantgroup`"
        else:
            self.fail(f"Unexpected database backend {settings.DATABASES['default']['ENGINE']}.")

        initial_tenant_group = tenancy_models.TenantGroup.objects.create(name="Old tenants")
        updated_tenant_group = tenancy_models.TenantGroup.objects.create(name="New tenants")
        for i in range(3):
            tenancy_models.Tenant.objects.create(name=f"Tenant {i}", group=initial_tenant_group)

        adapter = TestAdapter(job=None, sync=None)
        adapter.load()

        with CaptureQueriesContext(connection) as ctx:
            for i, tenant in enumerate(adapter.get_all("tenant")):
                tenant.update({"group__name": updated_tenant_group.name})
            tenant_group_queries = [query["sql"] for query in ctx.captured_queries if query_filter in query["sql"]]
            # One query to get the tenant group into the cache and another query per tenant during `clean`.
            self.assertEqual(4, len(tenant_group_queries))
        # As a consequence, there should be two cache hits for 'tenancy.tenantgroup'.
        self.assertEqual(2, adapter._cache_hits["tenancy.tenantgroup"])  # pylint: disable=protected-access

        with CaptureQueriesContext(connection) as ctx:
            for i, tenant in enumerate(adapter.get_all("tenant")):
                adapter.invalidate_cache()
                tenant.update({"group__name": updated_tenant_group.name})
            tenant_group_queries = [query["sql"] for query in ctx.captured_queries if query_filter in query["sql"]]
            # One query per tenant to re-populate the cache and another query per tenant during `clean`.
            self.assertEqual(6, len(tenant_group_queries))


class BaseModelIdentifierTest(TestCase):
    """Test cases for testing various things as identifiers for models."""

    @classmethod
    def setUpTestData(cls):
        custom_field_label = "Preferred ice cream flavour"
        cls.custom_field = extras_models.CustomField.objects.create(
            label=custom_field_label, description="The preferred flavour of ice cream for the reps for this provider"
        )
        cls.custom_field.content_types.add(ContentType.objects.get_for_model(circuits_models.Provider))
        provider_name = "Link Inc."
        provider_flavour = "Vanilla"
        cls.provider = circuits_models.Provider.objects.create(
            name=provider_name, _custom_field_data={cls.custom_field.name: provider_flavour}
        )

    def test_custom_field_in_identifiers(self):
        """Test the basic case where a custom field is part of the identifiers of a diffsync model."""
        custom_field_name = self.custom_field.name

        class _ProviderTestModel(NautobotModel):
            _model = circuits_models.Provider
            _modelname = "provider"
            _identifiers = ("name", "flavour")
            _attributes = ()

            name: str
            flavour: Annotated[str, CustomFieldAnnotation(name=custom_field_name)]

        diffsync_provider = _ProviderTestModel(
            name=self.provider.name,
            flavour=self.provider._custom_field_data[self.custom_field.name],  # pylint: disable=protected-access
        )
        diffsync_provider.diffsync = NautobotAdapter(job=None)

        self.assertEqual(self.provider, diffsync_provider.get_from_db())


class AnnotationsSubclassingTest(TestCase):
    """Test that annotations work properly with subclassing."""

    def test_annotations_subclassing(self):
        """Test that annotations work properly with subclassing."""

        class BaseTenantModel(NautobotModel):
            """Tenant model to be subclassed."""

            _model = tenancy_models.Tenant
            _modelname = "tenant"
            _identifiers = ("name",)
            _attributes = ("tags",)

            name: str
            tags: List[TagDict]

        class Subclass(BaseTenantModel):
            """Subclassed model."""

            extra_field: Optional[str] = None

        class Adapter(NautobotAdapter):
            """Test adapter."""

            tenant = Subclass
            top_level = ["tenant"]

        tenancy_models.Tenant.objects.create(name="Test Tenant")

        adapter = Adapter(job=None)
        try:
            adapter.load()
        except KeyError as error:
            if error.args[0] == "tags":
                self.fail("Don't use `Klass.__annotations__`, prefer `typing.get_type_hints`.")
            else:
                raise error
