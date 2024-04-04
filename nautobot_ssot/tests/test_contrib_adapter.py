"""Tests for contrib.NautobotAdapter."""

from typing import List
from unittest import skip
from unittest.mock import MagicMock

from diffsync import ObjectNotFound
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.db import connection
from django.test.utils import CaptureQueriesContext
from nautobot.core.testing import TestCase
from nautobot.circuits import models as circuits_models

from nautobot.dcim import models as dcim_models
from nautobot.extras import models as extras_models
from nautobot.extras.choices import RelationshipTypeChoices
from nautobot.ipam import models as ipam_models
from nautobot.tenancy import models as tenancy_models
from typing_extensions import Annotated, TypedDict

from nautobot_ssot.contrib import NautobotAdapter, NautobotModel, CustomFieldAnnotation
from nautobot_ssot.tests.contrib_base_classes import (
    TestCaseWithDeviceData,
    NautobotDevice,
    NautobotCable,
    TestAdapter,
    NautobotTenantGroup,
    NautobotTenant,
    TenantModelCustomRelationship,
    ProviderModelCustomRelationship,
)


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
        self.assertEqual(self.ip_address_1.mask_length, diffsync_device.primary_ip4__mask_length)


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
        cls.tenant = tenancy_models.Tenant.objects.create(name=cls.tenant_name, tenant_group=cls.tenant_group)
        cls.tags = [{"name": "space"}, {"name": "earth"}]
        for tag_dict in cls.tags:
            tag_object = extras_models.Tag.objects.create(name=tag_dict["name"])
            tag_object.content_types.set([ContentType.objects.get_for_model(tenancy_models.Tenant)])
            cls.tenant.tags.add(tag_object)

        cls.custom_field = extras_models.CustomField.objects.create(key="Test", label="Test")
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
            label="Test Relationship",
            source_type=ContentType.objects.get_for_model(circuits_models.Provider),
            destination_type=ContentType.objects.get_for_model(tenancy_models.Tenant),
            type=RelationshipTypeChoices.TYPE_ONE_TO_MANY,
        )
        self.tenant = tenancy_models.Tenant.objects.create(name="Test Tenant")
        self.provider = circuits_models.Provider.objects.create(name="Test Provider")
        extras_models.RelationshipAssociation.objects.create(
            relationship=self.relationship,
            source=self.provider,
            destination=self.tenant,
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
            tenancy_models.Tenant.objects.create(name=f"Tenant {i}", tenant_group=initial_tenant_group)

        adapter = TestAdapter(job=None, sync=None)
        adapter.load()

        with CaptureQueriesContext(connection) as ctx:
            for i, tenant in enumerate(adapter.get_all("tenant")):
                tenant.update({"tenant_group__name": updated_tenant_group.name})
            tenant_group_queries = [query["sql"] for query in ctx.captured_queries if query_filter in query["sql"]]
            # One query to get the tenant group into the cache and another query per tenant during `clean`.
            self.assertEqual(4, len(tenant_group_queries))
        # As a consequence, there should be two cache hits for 'tenancy.tenantgroup'.
        self.assertEqual(2, adapter._cache_hits["tenancy.tenantgroup"])  # pylint: disable=protected-access

        with CaptureQueriesContext(connection) as ctx:
            for i, tenant in enumerate(adapter.get_all("tenant")):
                adapter.invalidate_cache()
                tenant.update({"tenant_group__name": updated_tenant_group.name})
            tenant_group_queries = [query["sql"] for query in ctx.captured_queries if query_filter in query["sql"]]
            # One query per tenant to get the tenant group, one to pre-populate the cache, and another query per tenant during `clean`.
            self.assertEqual(6, len(tenant_group_queries))


class TestNestedRelationships(TestCase):
    """Tests for nested relationships."""

    def test_foreign_key_in_many_to_many_field(self):
        """Test that many to many fields can contain foreign keys."""

        class VLANDict(TypedDict):
            """Test VLAN dict."""

            id: int
            location__name: str

        class VLANGroupModel(NautobotModel):
            """Test VLAN Group model."""

            _model = ipam_models.VLANGroup
            _modelname = "vlan_group"
            _identifiers = ("name",)
            _attributes = ("vlans",)

            name: str
            vlans: List[VLANDict] = []

        class Adapter(NautobotAdapter):
            """Test adapter."""

            vlan_group = VLANGroupModel
            top_level = ["vlan_group"]

        location_type = dcim_models.LocationType.objects.create(name="Building")
        location_type.content_types.add(ContentType.objects.get_for_model(ipam_models.VLAN))
        location = dcim_models.Location.objects.create(
            name="Example Building", location_type=location_type, status=extras_models.Status.objects.get(name="Active")
        )
        group = ipam_models.VLANGroup.objects.create(name="Test VLAN Group")
        amount_of_vlans = 5
        for i in range(amount_of_vlans):
            ipam_models.VLAN.objects.create(
                vlan_group=group,
                vid=i,
                name=f"VLAN {i}",
                status=extras_models.Status.objects.get(name="Active"),
                location=location,
            )

        adapter = Adapter(job=MagicMock())
        adapter.load()

        diffsync_vlan_group = adapter.get_all("vlan_group")[0]

        self.assertEqual(amount_of_vlans, len(diffsync_vlan_group.vlans))
        for vlan in diffsync_vlan_group.vlans:
            self.assertEqual(location.name, vlan["location__name"])
