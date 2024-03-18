"""Tests for contrib.NautobotModel."""
from unittest import skip
from unittest.mock import MagicMock
from typing import Optional, List

from diffsync.exceptions import ObjectNotCreated, ObjectNotUpdated, ObjectNotDeleted
from django.contrib.contenttypes.models import ContentType
from nautobot.circuits import models as circuits_models
from nautobot.dcim import models as dcim_models
from nautobot.dcim.choices import InterfaceTypeChoices
from nautobot.extras.choices import RelationshipTypeChoices
from nautobot.extras import models as extras_models
from nautobot.ipam import models as ipam_models
from nautobot.tenancy import models as tenancy_models
from nautobot.utilities.testing import TestCase
from typing_extensions import Annotated

from nautobot_ssot.contrib import (
    NautobotAdapter,
    NautobotModel,
    CustomFieldAnnotation,
)
from nautobot_ssot.tests.contrib_base_classes import (
    NautobotTenant,
    TestCaseWithDeviceData,
    TagModel,
    TagDict,
    TenantModelCustomRelationship,
    ProviderModelCustomRelationship,
)
from nautobot_ssot.tests.test_contrib_adapter import (
    CustomRelationShipTestAdapterSource,
    CustomRelationShipTestAdapterDestination,
)


class BaseModelErrorTests(TestCase):
    """Testing various error cases for 'NautobotModel'."""

    def test_error_creation(self):
        """Test that different cases raise `ObjectNotCreated` correctly."""
        for ids, attrs, expected_error_prefix in [
            # Non-nullable field set to null
            ({"name": None}, {}, "Validated save failed for Django object"),
            # Foreign key reference doesn't exist
            (
                {"name": "Test Tenant"},
                {"group__name": "I don't exist"},
                "Couldn't find 'tenant group' instance behind 'group'",
            ),
            # Many to many reference doesn't exist
            (
                {"name": "Test Tenant"},
                {"tags": [{"name": "I don't exist"}]},
                "Unable to populate many to many relationship 'tags'",
            ),
            # Validation error because description is too long
            ({"name": "Test Tenant"}, {"description": "a" * 1000}, "Validated save failed for Django object"),
        ]:
            with self.subTest(ids=ids, attrs=attrs):
                with self.assertRaises(ObjectNotCreated) as exception_context:
                    NautobotTenant.create(diffsync=NautobotAdapter(job=MagicMock()), ids=ids, attrs=attrs)
                error_message = exception_context.exception.args[0].args[0]
                self.assertTrue(
                    error_message.startswith(expected_error_prefix),
                    f"Correct exception was raised but its error message doesn't start with '{expected_error_prefix}': '{error_message}'.",
                )

    def test_error_update(self):
        """Test that different cases raise `ObjectNotUpdated` correctly."""
        tenant = tenancy_models.Tenant.objects.create(name="Test Tenant")
        for base_parameters, updated_attrs, expected_error_prefix in [
            # Foreign key reference doesn't exist
            (
                {"name": tenant.name},
                {"group__name": "I don't exist"},
                "Couldn't find 'tenant group' instance behind 'group'",
            ),
            # Many to many reference doesn't exist
            (
                {"name": tenant.name},
                {"tags": [{"name": "I don't exist"}]},
                "Unable to populate many to many relationship 'tags'",
            ),
            # Validation error because description is too long
            ({"name": tenant.name}, {"description": "a" * 1000}, "Validated save failed for Django object"),
        ]:
            with self.subTest(base_parameters=base_parameters, updated_attrs=updated_attrs):
                diffsync_tenant = NautobotTenant(pk=tenant.pk, **base_parameters)
                diffsync_tenant.diffsync = NautobotAdapter(job=MagicMock())
                with self.assertRaises(ObjectNotUpdated) as exception_context:
                    diffsync_tenant.update(attrs=updated_attrs)
                error_message = exception_context.exception.args[0].args[0]
                self.assertTrue(
                    error_message.startswith(expected_error_prefix),
                    f"Correct exception was raised but its error message doesn't start with '{expected_error_prefix}': '{error_message}'.",
                )

    def test_error_delete(self):
        """Test that delete raises `ObjectNotDeleted` correctly."""
        tenant = tenancy_models.Tenant.objects.create(name="Test Tenant")
        location_type = dcim_models.LocationType.objects.create(name="Test Location Type")
        dcim_models.Location.objects.create(
            location_type=location_type,
            name="Test Site",
            tenant=tenant,
            status=extras_models.Status.objects.get(name="Active"),
        )
        diffsync_tenant = NautobotTenant(pk=tenant.pk, name=tenant.name)
        diffsync_tenant.diffsync = NautobotAdapter(job=MagicMock())
        with self.assertRaises(ObjectNotDeleted) as exception_context:
            diffsync_tenant.delete()
        error_message = exception_context.exception.args[0]
        expected_error_prefix = f"Couldn't delete {tenant.name} as it is referenced by another object"
        self.assertTrue(
            error_message.startswith(expected_error_prefix),
            f"Correct exception was raised but its error message doesn't start with '{expected_error_prefix}': '{error_message}'.",
        )


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
        diffsync_tenant = NautobotTenant(name=self.tenant_name, pk=tenant.pk)
        diffsync_tenant.diffsync = NautobotAdapter(job=None, sync=None)
        diffsync_tenant.update(attrs={"description": description})
        tenant.refresh_from_db()
        self.assertEqual(
            tenant.description, description, "Basic object updating through 'NautobotModel' does not work."
        )

    def test_basic_deletion(self):
        """Test whether basic deletion of an object works."""
        tenant = tenancy_models.Tenant.objects.create(name=self.tenant_name)

        diffsync_tenant = NautobotTenant(name=self.tenant_name, pk=tenant.pk)
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

        diffsync_provider = ProviderModel(name=provider_name, pk=provider.pk)
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

        diffsync_tenant = NautobotTenant(name=self.tenant_name, pk=tenant.pk)
        diffsync_tenant.diffsync = NautobotAdapter(job=None, sync=None)
        diffsync_tenant.update(attrs={"group__name": self.tenant_group_name})

        tenant.refresh_from_db()
        self.assertEqual(group, tenant.group, "Foreign key update from None through 'NautobotModel' does not work.")

    def test_foreign_key_remove(self):
        """Test whether unsetting a foreign key works."""
        group = tenancy_models.TenantGroup.objects.create(name=self.tenant_group_name)
        tenant = tenancy_models.Tenant.objects.create(name=self.tenant_name, group=group)

        diffsync_tenant = NautobotTenant(name=self.tenant_name, tenant_group__name=self.tenant_group_name, pk=tenant.pk)
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
            pk=prefix.pk,
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


class BaseModelCustomRelationshipOneToManyTest(TestCase):
    """Tests for manipulating custom relationships through the shared base model code."""

    @classmethod
    def setUpTestData(cls):
        cls.relationship = extras_models.Relationship.objects.create(
            name="Test Relationship",
            type=RelationshipTypeChoices.TYPE_ONE_TO_MANY,
            source_type=ContentType.objects.get_for_model(circuits_models.Provider),
            destination_type=ContentType.objects.get_for_model(tenancy_models.Tenant),
        )
        cls.tenant_one = tenancy_models.Tenant.objects.create(name="Test Tenant 1")
        cls.tenant_two = tenancy_models.Tenant.objects.create(name="Test Tenant 2")
        cls.provider_one = circuits_models.Provider.objects.create(name="Test Provider 1")
        cls.provider_two = circuits_models.Provider.objects.create(name="Test Provider 2")

    def test_custom_relationship_add_foreign_key(self):
        diffsync_tenant = TenantModelCustomRelationship(
            name=self.tenant_one.name,
            pk=self.tenant_one.pk,
        )
        diffsync_tenant.diffsync = CustomRelationShipTestAdapterDestination(job=MagicMock())
        diffsync_tenant.update({"provider__name": self.provider_one.name})
        self.assertEqual(extras_models.RelationshipAssociation.objects.count(), 1)

    def test_custom_relationship_update_foreign_key(self):
        diffsync_tenant = TenantModelCustomRelationship(
            name=self.tenant_one.name,
            pk=self.tenant_one.pk,
        )
        diffsync_tenant.diffsync = CustomRelationShipTestAdapterDestination(job=MagicMock())
        diffsync_tenant.update({"provider__name": self.provider_one.name})
        diffsync_tenant.update({"provider__name": self.provider_two.name})
        self.assertEqual(extras_models.RelationshipAssociation.objects.first().source, self.provider_two)

    def test_custom_relationship_add_to_many(self):
        diffsync_provider = ProviderModelCustomRelationship(
            name=self.provider_one.name,
            pk=self.provider_one.pk,
        )
        diffsync_provider.diffsync = CustomRelationShipTestAdapterSource(job=MagicMock())
        diffsync_provider.update({"tenants": [{"name": self.tenant_one.name}, {"name": self.tenant_two.name}]})
        self.assertEqual(extras_models.RelationshipAssociation.objects.count(), 2)

    def test_custom_relationship_update_to_many(self):
        diffsync_provider = ProviderModelCustomRelationship(
            name=self.provider_one.name,
            pk=self.provider_one.pk,
        )
        diffsync_provider.diffsync = CustomRelationShipTestAdapterSource(job=MagicMock())
        diffsync_provider.update({"tenants": [{"name": self.tenant_one.name}]})
        diffsync_provider.update({"tenants": [{"name": self.tenant_two.name}]})
        self.assertEqual(extras_models.RelationshipAssociation.objects.count(), 1)
        self.assertEqual(extras_models.RelationshipAssociation.objects.first().destination, self.tenant_two)


class BaseModelCustomRelationshipTestWithDeviceData(TestCaseWithDeviceData):
    """Tests for NautobotModel with custom relationships and including device data."""

    def test_create_with_custom_relationship(self):
        """Test that NautobotModel.create works as expected with custom relationships."""

        class CableModel(NautobotModel):
            """Shared data model representing a Cable."""

            _model = dcim_models.Cable
            _modelname = "cable"
            _identifiers = (
                "termination_a__device__name",
                "termination_a__name",
                "termination_a__app_label",
                "termination_a__model",
                "termination_b__device__name",
                "termination_b__name",
                "termination_b__app_label",
                "termination_b__model",
            )
            _attributes = ("status__name",)
            _children = {}

            termination_a__device__name: str
            termination_a__name: str
            termination_a__app_label: str
            termination_a__model: str
            termination_b__device__name: str
            termination_b__name: str
            termination_b__app_label: str
            termination_b__model: str
            status__name: str

        device = dcim_models.Device.objects.first()
        interface_a = dcim_models.Interface.objects.create(
            device=device,
            status=extras_models.Status.objects.get(name="Active"),
            name="interface_a",
            type=InterfaceTypeChoices.TYPE_1GE_FIXED,
        )
        interface_b = dcim_models.Interface.objects.create(
            device=device,
            status=extras_models.Status.objects.get(name="Active"),
            name="interface_b",
            type=InterfaceTypeChoices.TYPE_1GE_FIXED,
        )

        CableModel.create(
            diffsync=NautobotAdapter(job=MagicMock()),
            ids={
                "termination_a__device__name": device.name,
                "termination_a__name": interface_a.name,
                "termination_a__app_label": "dcim",
                "termination_a__model": "interface",
                "termination_b__device__name": device.name,
                "termination_b__name": interface_b.name,
                "termination_b__app_label": "dcim",
                "termination_b__model": "interface",
            },
            attrs={
                "status__name": "Connected",
            },
        )


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

        diffsync_tenant = NautobotTenant(name=self.tenant_name, tags=[{"name": self.tags[0].name}], pk=tenant.pk)
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

        diffsync_tenant = NautobotTenant(
            name=self.tenant_name, tags=[{"name": tag.name} for tag in self.tags], pk=tenant.pk
        )
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

        diffsync_tenant = NautobotTenant(
            name=self.tenant_name, tags=[{"name": tag.name} for tag in self.tags], pk=tenant.pk
        )
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
        tag_diffsync = TagModel(name=name, pk=tag.pk)
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

        tag_diffsync = TagModel(name=name, pk=tag.pk)
        tag_diffsync.diffsync = NautobotAdapter(job=None, sync=None)
        tag_diffsync.update(attrs={"content_types": []})

        tag.refresh_from_db()
        self.assertEqual(
            list(tag.content_types.values("app_label", "model")),
            [],
            "Removing objects to a many-to-many relationship based on more than one parameter through 'NautobotModel'"
            "does not work.",
        )


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
