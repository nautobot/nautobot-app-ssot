"""Tests for contrib.NautobotAdapter."""

from typing import Annotated, List, Optional
from unittest import skip
from unittest.mock import MagicMock

from diffsync import ObjectNotFound
from diffsync.exceptions import ObjectCrudException
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.db import connection
from django.test.utils import CaptureQueriesContext
from nautobot.apps.choices import RelationshipTypeChoices
from nautobot.apps.testing import TestCase
from nautobot.circuits import models as circuits_models
from nautobot.dcim import models as dcim_models
from nautobot.extras import models as extras_models
from nautobot.ipam import models as ipam_models
from nautobot.tenancy import models as tenancy_models
from typing_extensions import TypedDict

from nautobot_ssot.contrib import (
    CustomFieldAnnotation,
    NautobotAdapter,
    NautobotModel,
)
from nautobot_ssot.tests.contrib.base import (
    NautobotCable,
    NautobotDevice,
    NautobotDeviceBay,
    NautobotDeviceInvalidChildAttr,
    NautobotDeviceWithChildBay,
    NautobotTenant,
    NautobotTenantGroup,
    ProviderModelCustomRelationship,
    TenantModelCustomManyTomanyRelationship,
    TenantModelCustomRelationship,
    TenantToOneProviderModel,
    TestAdapter,
    TestCaseWithDeviceData,
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
        interface = dcim_models.Interface.objects.get(name="Ethernet1", device=device)
        interface.ip_addresses.add(self.ip_address_1)
        device.primary_ip4 = self.ip_address_1
        device.validated_save()

        adapter = Adapter(job=MagicMock())
        adapter.load()
        diffsync_device = adapter.get(NautobotDevice, {"name": device.name})

        self.assertEqual(self.ip_address_1.host, diffsync_device.primary_ip4__host)
        self.assertEqual(self.ip_address_1.mask_length, diffsync_device.primary_ip4__mask_length)

    def test_one_to_one_relationship_children(self):
        """Test that loading a one-to-one relationship works in children."""

        class Adapter(NautobotAdapter):
            """Adapter for loading one-to-one relationship fields on a device children."""

            top_level = ("device",)
            device = NautobotDeviceWithChildBay
            device_bay = NautobotDeviceBay

        device = dcim_models.Device.objects.first()
        parent_device = dcim_models.Device.objects.last()
        dcim_models.DeviceBay.objects.create(name="Slot0", device=parent_device, installed_device=device)

        adapter = Adapter(job=MagicMock())
        adapter.load()
        diffsync_device = adapter.get(NautobotDeviceWithChildBay, {"name": device.name})
        self.assertTrue(device.parent_bay.name in diffsync_device.parent_bay[0])

    def test_invalid_children_attr_raises(self):
        """Test that invalid attribute name in _children raises AttributeError."""

        class Adapter(NautobotAdapter):
            """Adapter with invalid children field."""

            top_level = ("device",)
            device = NautobotDeviceInvalidChildAttr
            device_bay = NautobotDeviceBay

        adapter = Adapter(job=MagicMock())
        with self.assertRaises(AttributeError):
            adapter.load()


class NautobotAdapterGenericRelationTests(TestCaseWithDeviceData):
    """Testing the generic relation capability of the 'NautobotAdapter' class."""

    def setUp(self):
        dcim_models.Cable.objects.create(
            termination_a=dcim_models.Interface.objects.all().filter(name="Ethernet1").first(),
            termination_b=dcim_models.Interface.objects.all().filter(name="Ethernet1").last(),
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
            "termination_a__name": "Ethernet1",
            "termination_a__device__name": "sw01",
            "termination_b__app_label": "dcim",
            "termination_b__model": "interface",
            "termination_b__name": "Ethernet1",
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

    def test_custom_field_annotation_fallback_via_load(self):
        """
        Test that the adapter correctly loads a custom field value using the 'name' fallback
        when the CustomFieldAnnotation 'key' is None by calling the public load() method.
        """

        custom_field, _ = extras_models.CustomField.objects.update_or_create(
            key="fallback_test",
            defaults={"label": "Custom Field for fallback test"},
        )
        custom_field.content_types.set([ContentType.objects.get_for_model(tenancy_models.Tenant)])

        tenant_obj, _ = tenancy_models.Tenant.objects.update_or_create(name="Tenant for fallback test")
        tenant_obj._custom_field_data["fallback_test"] = "Expected value for fallback test"  # pylint: disable=protected-access
        tenant_obj.save()

        class TestModel(NautobotModel):
            """Test model"""

            _model = tenancy_models.Tenant
            _modelname = "tenant"
            _identifiers = ("name",)
            _attributes = ("custom_field",)

            name: str
            custom_field: Annotated[Optional[str], CustomFieldAnnotation(name="fallback_test", key=None)] = None

        class Adapter(NautobotAdapter):
            """Test adapter"""

            top_level = ["tenant"]
            tenant = TestModel

        adapter = Adapter(job=MagicMock())
        adapter.load()

        loaded_model = adapter.get(TestModel, "Tenant for fallback test")
        self.assertEqual(loaded_model.custom_field, "Expected value for fallback test")


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
        self.assertEqual(2, adapter.cache.hits("tenancy.tenantgroup"))  # pylint: disable=protected-access

        with CaptureQueriesContext(connection) as ctx:
            for i, tenant in enumerate(adapter.get_all("tenant")):
                adapter.cache.invalidate_cache()
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

            vid: int
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


class AdapterCustomRelationshipSortingTest(NautobotAdapter):
    """Adapter for testing custom many-to-many relationship sorting."""

    top_level = ["tenant"]
    tenant = TenantModelCustomManyTomanyRelationship
    sorted_relationships = (
        (
            "tenant",
            "tenants",
            "name",
        ),
    )


class CustomFieldAnnotationValidationTest(TestCase):
    """Cover validation on the CustomFieldAnnotation dataclass."""

    def test_requires_key_or_name(self):
        """A CustomFieldAnnotation with neither 'key' nor 'name' raises ValueError."""
        with self.assertRaises(ValueError):
            CustomFieldAnnotation()


class NautobotAdapterUtilityCoverageTests(TestCase):
    """Cover small utility / edge branches of NautobotAdapter."""

    def test_progress_logger_disabled_is_noop(self):
        """With the progress logger disabled, log_loaded_objects does nothing."""
        adapter = TestAdapter(job=MagicMock())
        adapter.enable_progress_logger = False
        adapter.log_loaded_objects()
        self.assertEqual(adapter.objects_loaded, 0)
        adapter.job.logger.info.assert_not_called()

    def test_progress_logger_logs_on_interval(self):
        """With the progress logger enabled, log_loaded_objects logs when the interval is hit."""
        adapter = TestAdapter(job=MagicMock())
        adapter.enable_progress_logger = True
        adapter.progress_logger_interval = 1
        adapter.log_loaded_objects()
        self.assertEqual(adapter.objects_loaded, 1)
        adapter.job.logger.info.assert_called_once()

    def test_validate_adapter_requires_top_level(self):
        """Instantiating an adapter without 'top_level' raises ValueError."""

        class NoTopLevelAdapter(NautobotAdapter):
            """Adapter missing the required 'top_level' attribute."""

        with self.assertRaises(ValueError):
            NoTopLevelAdapter(job=MagicMock())

    def test_get_parameter_names(self):
        """_get_parameter_names returns the model's synced attributes."""
        self.assertEqual(
            NautobotAdapter._get_parameter_names(NautobotTenant),  # pylint: disable=protected-access
            NautobotTenant.get_synced_attributes(),
        )

    def test_invalidate_cache_is_deprecated(self):
        """The deprecated invalidate_cache method logs a warning and delegates to the cache."""
        adapter = TestAdapter(job=MagicMock())
        adapter.invalidate_cache()
        adapter.job.logger.warning.assert_called_once()

    def test_get_diffsync_class_missing_attribute(self):
        """Requesting a diffsync class not defined on the adapter raises AttributeError.

        (diffsync validates 'top_level' at class-definition time, so this is exercised via a
        direct call, mirroring how child-model names are resolved at runtime.)
        """
        adapter = TestAdapter(job=MagicMock())
        with self.assertRaises(AttributeError):
            adapter._get_diffsync_class("does_not_exist")  # pylint: disable=protected-access


class NautobotAdapterCustomLoaderTest(TestCase):
    """Cover the per-parameter custom loader (load_param_<field>) branch."""

    def test_load_param_custom_loader(self):
        """A 'load_param_<field>' method on the adapter overrides the loaded value."""

        class TenantModel(NautobotModel):
            """Tenant model with a normal field served by a custom loader."""

            _model = tenancy_models.Tenant
            _modelname = "tenant"
            _identifiers = ("name",)
            _attributes = ("description",)

            name: str
            description: Optional[str] = None

        class Adapter(NautobotAdapter):
            """Adapter providing a custom loader for 'description'."""

            top_level = ("tenant",)
            tenant = TenantModel

            def load_param_description(self, _parameter_name, _database_object):
                """Return a fixed value to exercise the custom-loader branch."""
                return "custom-loaded"

        tenancy_models.Tenant.objects.create(name="LoaderTenant", description="original")
        adapter = Adapter(job=MagicMock())
        adapter.load()
        self.assertEqual(adapter.get(TenantModel, "LoaderTenant").description, "custom-loaded")


class NautobotAdapterPydanticErrorTest(TestCase):
    """Cover the pydantic-ValidationError -> ValueError translation during load."""

    def test_pydantic_validation_error_becomes_value_error(self):
        """A value that fails pydantic validation during load is re-raised as ValueError."""

        class BadTenantModel(NautobotModel):
            """Model whose 'description' is typed int, but the DB holds a non-numeric string."""

            _model = tenancy_models.Tenant
            _modelname = "tenant"
            _identifiers = ("name",)
            _attributes = ("description",)

            name: str
            description: int

        class Adapter(NautobotAdapter):
            """Adapter for the deliberately mistyped model."""

            top_level = ("tenant",)
            tenant = BadTenantModel

        tenancy_models.Tenant.objects.create(name="BadTenant", description="not-an-int")
        adapter = Adapter(job=MagicMock())
        with self.assertRaises(ValueError):
            adapter.load()


class TenantToOneDestinationAdapter(NautobotAdapter):
    """Adapter loading the destination-side to-one custom relationship model."""

    top_level = ("tenant",)
    tenant = TenantToOneProviderModel


class NautobotAdapterCustomRelationshipEdgeTests(TestCase):
    """Cover the one-to-many DESTINATION and foreign-key custom-relationship edge branches."""

    def setUp(self):
        self.relationship = extras_models.Relationship.objects.create(
            label="Test Relationship",
            type=RelationshipTypeChoices.TYPE_ONE_TO_MANY,
            source_type=ContentType.objects.get_for_model(circuits_models.Provider),
            destination_type=ContentType.objects.get_for_model(tenancy_models.Tenant),
        )
        self.tenant = tenancy_models.Tenant.objects.create(name="Edge Tenant")

    def _associate(self, provider_name):
        provider = circuits_models.Provider.objects.create(name=provider_name)
        extras_models.RelationshipAssociation.objects.create(
            relationship=self.relationship, source=provider, destination=self.tenant
        )
        return provider

    def test_to_one_destination_without_association_is_none(self):
        """A destination-side to-one field with no association loads as None."""
        adapter = TenantToOneDestinationAdapter(job=MagicMock())
        adapter.load()
        self.assertIsNone(adapter.get(TenantToOneProviderModel, "Edge Tenant").provider)

    def test_to_one_destination_single_association(self):
        """A destination-side to-one field with one association loads as a single dict."""
        self._associate("Edge Provider")
        adapter = TenantToOneDestinationAdapter(job=MagicMock())
        adapter.load()
        self.assertEqual(adapter.get(TenantToOneProviderModel, "Edge Tenant").provider, {"name": "Edge Provider"})

    def test_to_one_destination_multiple_associations_raises(self):
        """More than one association for a one-to-many destination raises ObjectCrudException."""
        self._associate("Provider 1")
        self._associate("Provider 2")
        adapter = TenantToOneDestinationAdapter(job=MagicMock())
        with self.assertRaises(ObjectCrudException):
            adapter.load()

    def test_foreign_key_custom_relationship_without_association_is_none(self):
        """A foreign-key custom-relationship field with no association loads as None."""
        adapter = CustomRelationShipTestAdapterSource(job=MagicMock())
        adapter.load()
        self.assertIsNone(adapter.get(TenantModelCustomRelationship, "Edge Tenant").provider__name)

    def test_foreign_key_custom_relationship_multiple_associations_warns(self):
        """More than one association for a foreign-key custom relationship logs a warning."""
        self._associate("Provider 1")
        self._associate("Provider 2")
        adapter = CustomRelationShipTestAdapterSource(job=MagicMock())
        adapter.load()
        adapter.job.logger.warning.assert_called()
        self.assertIsNotNone(adapter.get(TenantModelCustomRelationship, "Edge Tenant").provider__name)


class _CoverageJobMeta:
    data_source = "Coverage Source"


class _CoverageJob:
    """Minimal job stand-in exposing Meta.data_source for get_or_create_metadatatype."""

    Meta = _CoverageJobMeta

    def __init__(self):
        self.logger = MagicMock()


class NautobotAdapterMetadataTypeChildrenTest(TestCase):
    """Cover the child-model loop in get_or_create_metadatatype."""

    def test_children_models_included(self):
        """get_or_create_metadatatype walks child models and records their scope fields."""
        adapter = TestAdapter(job=_CoverageJob())
        adapter.get_or_create_metadatatype()
        self.assertIsNotNone(adapter.metadata_type)
        # The top-level model and its child model both get scope fields recorded.
        self.assertIn(NautobotTenantGroup, adapter.metadata_scope_fields)
        self.assertIn(NautobotTenant, adapter.metadata_scope_fields)
