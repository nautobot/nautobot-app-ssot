"""Tests for contrib.NautobotModel."""

import uuid
from typing import Annotated, List, Optional
from unittest import skip
from unittest.mock import MagicMock, patch

from diffsync.exceptions import ObjectNotCreated, ObjectNotDeleted, ObjectNotUpdated
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import MultipleObjectsReturned
from nautobot.apps.testing import TestCase
from nautobot.circuits import models as circuits_models
from nautobot.dcim import models as dcim_models
from nautobot.dcim.choices import InterfaceTypeChoices
from nautobot.extras import models as extras_models
from nautobot.extras.choices import RelationshipTypeChoices
from nautobot.extras.models.metadata import MetadataType
from nautobot.ipam import models as ipam_models
from nautobot.tenancy import models as tenancy_models

from nautobot_ssot.contrib import (
    CustomFieldAnnotation,
    CustomRelationshipAnnotation,
    NautobotAdapter,
    NautobotModel,
    RelationshipSideEnum,
)
from nautobot_ssot.tests.contrib.adapter.test_adapter import (
    CustomRelationShipTestAdapterDestination,
    CustomRelationShipTestAdapterSource,
)
from nautobot_ssot.tests.contrib.base import (
    MockNautobotAdapter,
    NautobotCable,
    NautobotTenant,
    ProviderDict,
    ProviderModelCustomRelationship,
    TagDict,
    TagModel,
    TenantModelCustomRelationship,
    TenantToOneProviderModel,
    TestAdapter,
    TestCaseWithDeviceData,
)


class _CoverageJobMeta:
    data_source = "Test Source"


class _CoverageJob:
    """Minimal job stand-in exposing Meta.data_source for get_or_create_metadatatype."""

    Meta = _CoverageJobMeta

    def __init__(self):
        self.logger = MagicMock()


class BaseModelCustomRelationshipOneToManyTest(TestCase):
    """Tests for manipulating custom relationships through the shared base model code."""

    @classmethod
    def setUpTestData(cls):
        cls.relationship = extras_models.Relationship.objects.create(
            label="Test Relationship",
            type=RelationshipTypeChoices.TYPE_ONE_TO_MANY,
            source_type=ContentType.objects.get_for_model(circuits_models.Provider),
            destination_type=ContentType.objects.get_for_model(tenancy_models.Tenant),
        )
        cls.tenant_one = tenancy_models.Tenant.objects.create(name="Test Tenant 1")
        cls.tenant_two = tenancy_models.Tenant.objects.create(name="Test Tenant 2")
        cls.provider_one = circuits_models.Provider.objects.create(name="Test Provider 1")
        cls.provider_two = circuits_models.Provider.objects.create(name="Test Provider 2")

    def test_custom_relationship_add_foreign_key(self):
        adapter_tenant = TenantModelCustomRelationship(
            name=self.tenant_one.name,
            pk=self.tenant_one.pk,
        )
        adapter_tenant.adapter = CustomRelationShipTestAdapterDestination(job=MagicMock())
        adapter_tenant.update({"provider__name": self.provider_one.name})
        self.assertEqual(extras_models.RelationshipAssociation.objects.count(), 1)

    def test_custom_relationship_update_foreign_key(self):
        adapter_tenant = TenantModelCustomRelationship(
            name=self.tenant_one.name,
            pk=self.tenant_one.pk,
        )
        adapter_tenant.adapter = CustomRelationShipTestAdapterDestination(job=MagicMock())
        adapter_tenant.update({"provider__name": self.provider_one.name})
        adapter_tenant.update({"provider__name": self.provider_two.name})
        self.assertEqual(extras_models.RelationshipAssociation.objects.first().source, self.provider_two)

    def test_custom_relationship_add_to_many(self):
        diffsync_provider = ProviderModelCustomRelationship(
            name=self.provider_one.name,
            pk=self.provider_one.pk,
        )
        diffsync_provider.adapter = CustomRelationShipTestAdapterSource(job=MagicMock())
        diffsync_provider.update({"tenants": [{"name": self.tenant_one.name}, {"name": self.tenant_two.name}]})
        self.assertEqual(extras_models.RelationshipAssociation.objects.count(), 2)

    def test_custom_relationship_update_to_many(self):
        diffsync_provider = ProviderModelCustomRelationship(
            name=self.provider_one.name,
            pk=self.provider_one.pk,
        )
        diffsync_provider.adapter = CustomRelationShipTestAdapterSource(job=MagicMock())
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
            status=self.status_active,
            name="interface_a",
            type=InterfaceTypeChoices.TYPE_1GE_FIXED,
        )
        interface_b = dcim_models.Interface.objects.create(
            device=device,
            status=self.status_active,
            name="interface_b",
            type=InterfaceTypeChoices.TYPE_1GE_FIXED,
        )

        CableModel.create(
            adapter=MockNautobotAdapter(job=MagicMock()),
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

        adapter_tenant = NautobotTenant(name=self.tenant_name, tags=[{"name": self.tags[0].name}], pk=tenant.pk)
        adapter_tenant.adapter = MockNautobotAdapter(job=None, sync=None)
        adapter_tenant.update(attrs={"tags": [{"name": tag.name} for tag in self.tags]})

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

        adapter_tenant = NautobotTenant(
            name=self.tenant_name, tags=[{"name": tag.name} for tag in self.tags], pk=tenant.pk
        )
        adapter_tenant.adapter = MockNautobotAdapter(job=None, sync=None)
        adapter_tenant.update(attrs={"tags": [{"name": self.tags[0].name}]})

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

        adapter_tenant = NautobotTenant(
            name=self.tenant_name, tags=[{"name": tag.name} for tag in self.tags], pk=tenant.pk
        )
        adapter_tenant.adapter = MockNautobotAdapter(job=None, sync=None)
        adapter_tenant.update(attrs={"tags": []})

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
        tag_diffsync.adapter = MockNautobotAdapter(job=None, sync=None)
        tag_diffsync.update(attrs={"content_types": content_types})

        tag.refresh_from_db()
        self.assertCountEqual(
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
        tag_diffsync.adapter = MockNautobotAdapter(job=None, sync=None)
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


class QuerySetPrefetchRelatedTest(TestCase):
    """Test that _get_queryset adds expected prefetch_related params to the queryset."""

    @patch("django.db.models.query.QuerySet.prefetch_related")
    def test__get_queryset(self, prefetch_related_mock):
        """Test that _get_queryset adds expected prefetch_related params to the queryset."""

        class BaseIPAddressModel(NautobotModel):
            """Test contrib model."""

            _model = ipam_models.IPAddress
            _modelname = "ipaddress"
            _identifiers = ("host", "mask_length", "parent__namespace__name")
            _attributes = ("status__name", "tenant__name")

            host: str
            mask_length: int
            parent__namespace__name: str
            status__name: str
            tenant__name: str

        BaseIPAddressModel._get_queryset()  # pylint: disable=protected-access
        prefetch_related_mock.assert_called_with("parent__namespace", "status", "tenant")


class BaseModelCrudErrorBranchTests(TestCase):
    """Cover the naturally-reachable CRUD error/edge branches of NautobotModel."""

    def test_create_with_unknown_field_raises(self):
        """A parameter not defined on the DiffSync model raises via `_check_field`."""
        with self.assertRaises(ObjectNotCreated):
            NautobotTenant.create(MockNautobotAdapter(job=MagicMock()), {"name": "T"}, {"not_a_field": "x"})

    def test_update_missing_object_raises(self):
        """Updating a DiffSync object whose pk is absent from the DB raises ObjectNotUpdated."""
        diffsync_tenant = NautobotTenant(name="ghost", pk=uuid.uuid4())
        diffsync_tenant.adapter = MockNautobotAdapter(job=MagicMock())
        with self.assertRaises(ObjectNotUpdated):
            diffsync_tenant.update({"description": "x"})

    def test_delete_missing_object_raises(self):
        """Deleting a DiffSync object whose pk is absent from the DB raises ObjectNotDeleted."""
        diffsync_tenant = NautobotTenant(name="ghost", pk=uuid.uuid4())
        diffsync_tenant.adapter = MockNautobotAdapter(job=MagicMock())
        with self.assertRaises(ObjectNotDeleted):
            diffsync_tenant.delete()

    def test_update_writes_last_sync_metadata(self):
        """When the adapter has a metadata_type, update() stamps last-sync ObjectMetadata."""
        tenant = tenancy_models.Tenant.objects.create(name="MetaTenant")
        adapter = TestAdapter(job=_CoverageJob())
        adapter.get_or_create_metadatatype()
        diffsync_tenant = NautobotTenant(name="MetaTenant", pk=tenant.pk)
        diffsync_tenant.adapter = adapter
        diffsync_tenant.update({"description": "updated"})
        self.assertTrue(tenant.associated_object_metadata.filter(metadata_type=adapter.metadata_type).exists())


class _ProviderFKSourceModel(NautobotModel):
    """Provider with a SOURCE-side custom-relationship foreign key (Provider -> Tenant)."""

    _model = circuits_models.Provider
    _modelname = "provider"
    _identifiers = ("name",)
    _attributes = ("tenant__name",)

    name: str
    tenant__name: Annotated[
        Optional[str], CustomRelationshipAnnotation(name="Test Relationship", side=RelationshipSideEnum.SOURCE)
    ] = None


class _ProviderFKSourceAdapter(NautobotAdapter):
    top_level = ("provider",)
    provider = _ProviderFKSourceModel


class _TenantToOneProviderAdapter(NautobotAdapter):
    top_level = ("tenant",)
    tenant = TenantToOneProviderModel


class _TenantM2MProvidersModel(NautobotModel):
    """Tenant with a DESTINATION-side many-to-many custom relationship to Providers."""

    _model = tenancy_models.Tenant
    _modelname = "tenant"
    _identifiers = ("name",)
    _attributes = ("providers",)

    name: str
    providers: Annotated[
        List[ProviderDict],
        CustomRelationshipAnnotation(name="M2M Relationship", side=RelationshipSideEnum.DESTINATION),
    ] = []


class _TenantM2MProvidersAdapter(NautobotAdapter):
    top_level = ("tenant",)
    tenant = _TenantM2MProvidersModel


class BaseModelCustomRelationshipBranchTests(TestCase):
    """Cover custom-relationship write branches not exercised by the existing tests."""

    @classmethod
    def setUpTestData(cls):
        cls.one_to_many = extras_models.Relationship.objects.create(
            label="Test Relationship",
            type=RelationshipTypeChoices.TYPE_ONE_TO_MANY,
            source_type=ContentType.objects.get_for_model(circuits_models.Provider),
            destination_type=ContentType.objects.get_for_model(tenancy_models.Tenant),
        )
        cls.many_to_many = extras_models.Relationship.objects.create(
            label="M2M Relationship",
            type=RelationshipTypeChoices.TYPE_MANY_TO_MANY,
            source_type=ContentType.objects.get_for_model(circuits_models.Provider),
            destination_type=ContentType.objects.get_for_model(tenancy_models.Tenant),
        )

    def test_source_side_foreign_key(self):
        """A SOURCE-side custom-relationship foreign key creates the association."""
        provider = circuits_models.Provider.objects.create(name="SrcProvider")
        tenancy_models.Tenant.objects.create(name="DestTenant")
        diffsync_provider = _ProviderFKSourceModel(name="SrcProvider", pk=provider.pk)
        diffsync_provider.adapter = _ProviderFKSourceAdapter(job=MagicMock())
        diffsync_provider.update({"tenant__name": "DestTenant"})
        self.assertEqual(extras_models.RelationshipAssociation.objects.filter(relationship=self.one_to_many).count(), 1)

    def test_source_side_foreign_key_missing_destination_raises(self):
        """A SOURCE-side custom-relationship foreign key to a missing object raises."""
        provider = circuits_models.Provider.objects.create(name="SrcProvider2")
        diffsync_provider = _ProviderFKSourceModel(name="SrcProvider2", pk=provider.pk)
        diffsync_provider.adapter = _ProviderFKSourceAdapter(job=MagicMock())
        with self.assertRaises(ObjectNotUpdated):
            diffsync_provider.update({"tenant__name": "NoSuchTenant"})

    def test_one_to_many_destination_to_one_write(self):
        """Writing a DESTINATION-side to-one custom-relationship field creates the association."""
        tenant = tenancy_models.Tenant.objects.create(name="DestTenant3")
        circuits_models.Provider.objects.create(name="SrcProvider3")
        diffsync_tenant = TenantToOneProviderModel(name="DestTenant3", pk=tenant.pk)
        diffsync_tenant.adapter = _TenantToOneProviderAdapter(job=MagicMock())
        diffsync_tenant.update({"provider": {"name": "SrcProvider3"}})
        self.assertEqual(extras_models.RelationshipAssociation.objects.filter(relationship=self.one_to_many).count(), 1)

    def test_destination_side_many_to_many(self):
        """Writing a DESTINATION-side many-to-many custom relationship creates associations."""
        tenant = tenancy_models.Tenant.objects.create(name="M2MTenant")
        circuits_models.Provider.objects.create(name="M2MProvider")
        diffsync_tenant = _TenantM2MProvidersModel(name="M2MTenant", pk=tenant.pk)
        diffsync_tenant.adapter = _TenantM2MProvidersAdapter(job=MagicMock())
        diffsync_tenant.update({"providers": [{"name": "M2MProvider"}]})
        self.assertEqual(
            extras_models.RelationshipAssociation.objects.filter(relationship=self.many_to_many).count(), 1
        )

    def test_foreign_key_missing_relationship_raises(self):
        """A custom-relationship foreign key whose Relationship does not exist raises."""
        tenant = tenancy_models.Tenant.objects.create(name="NoRelTenant")
        # Use a model referencing a relationship label that was never created.
        diffsync_tenant = TenantModelCustomRelationship(name="NoRelTenant", pk=tenant.pk)
        diffsync_tenant.adapter = CustomRelationShipTestAdapterDestination(job=MagicMock())
        self.one_to_many.delete()  # remove "Test Relationship" so the lookup fails
        with self.assertRaises(ObjectNotUpdated):
            diffsync_tenant.update({"provider__name": "whatever"})


class BaseModelGenericForeignKeyBranchTests(TestCaseWithDeviceData):
    """Cover the generic-foreign-key bad-content-type branch via a Cable model."""

    def test_generic_foreign_key_unknown_content_type_raises(self):
        """A generic FK pointing at a non-existent content type raises ObjectNotCreated.

        Uses the shared ``NautobotCable`` model (generic FK terminations); the content-type
        resolution fails before the object is saved, so a bad ``termination_a__model`` suffices.
        """
        with self.assertRaises(ObjectNotCreated):
            NautobotCable.create(
                MockNautobotAdapter(job=MagicMock()),
                {
                    "termination_a__name": "Ethernet1",
                    "termination_a__device__name": "sw01",
                    "termination_b__name": "Ethernet1",
                    "termination_b__device__name": "sw02",
                },
                {
                    "termination_a__app_label": "dcim",
                    "termination_a__model": "not_a_real_model",
                    "termination_b__app_label": "dcim",
                    "termination_b__model": "interface",
                },
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
                {"tenant_group__name": "I don't exist"},
                "Couldn't find 'tenant group' instance behind 'tenant_group'",
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
                    NautobotTenant.create(adapter=MockNautobotAdapter(job=MagicMock()), ids=ids, attrs=attrs)
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
                {"tenant_group__name": "I don't exist"},
                "Couldn't find 'tenant group' instance behind 'tenant_group'",
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
                diffsync_tenant.adapter = MockNautobotAdapter(job=MagicMock())
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
        diffsync_tenant.adapter = MockNautobotAdapter(job=MagicMock())
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
        NautobotTenant.create(adapter=None, ids={"name": self.tenant_name}, attrs={})
        try:
            tenancy_models.Tenant.objects.get(name=self.tenant_name)
        except tenancy_models.Tenant.DoesNotExist:
            self.fail("Basic object creation through 'NautobotModel' does not work.")

    def test_basic_update(self):
        """Test whether a basic update of an object works."""
        tenant = tenancy_models.Tenant.objects.create(name=self.tenant_name)
        description = "An updated description"
        diffsync_tenant = NautobotTenant(name=self.tenant_name, pk=tenant.pk)
        diffsync_tenant.adapter = MockNautobotAdapter(job=None, sync=None)
        diffsync_tenant.update(attrs={"description": description})
        tenant.refresh_from_db()
        self.assertEqual(
            tenant.description, description, "Basic object updating through 'NautobotModel' does not work."
        )

    def test_basic_deletion(self):
        """Test whether basic deletion of an object works."""
        tenant = tenancy_models.Tenant.objects.create(name=self.tenant_name)

        diffsync_tenant = NautobotTenant(name=self.tenant_name, pk=tenant.pk)
        diffsync_tenant.adapter = MockNautobotAdapter(job=None, sync=None)
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
            key="is_global", label=custom_field_name, type="boolean"
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
        diffsync_provider.adapter = MockNautobotAdapter(job=None, sync=None)
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
        diffsync_tenant.adapter = MockNautobotAdapter(job=None, sync=None)
        diffsync_tenant.update(attrs={"tenant_group__name": self.tenant_group_name})

        tenant.refresh_from_db()
        self.assertEqual(
            group, tenant.tenant_group, "Foreign key update from None through 'NautobotModel' does not work."
        )

    def test_foreign_key_remove(self):
        """Test whether unsetting a foreign key works."""
        group = tenancy_models.TenantGroup.objects.create(name=self.tenant_group_name)
        tenant = tenancy_models.Tenant.objects.create(name=self.tenant_name, tenant_group=group)

        diffsync_tenant = NautobotTenant(name=self.tenant_name, tenant_group__name=self.tenant_group_name, pk=tenant.pk)
        diffsync_tenant.adapter = MockNautobotAdapter(job=None, sync=None)
        diffsync_tenant.update(attrs={"tenant_group__name": None})

        tenant.refresh_from_db()
        self.assertEqual(None, tenant.tenant_group, "Foreign key update to None through 'NautobotModel' does not work.")

    def test_foreign_key_add_multiple_fields(self):
        """Test whether setting a foreign key identified by multiple fields works.

        Uses the self-referential ``Location.parent`` foreign key, whose target ``Location``
        is identified by both ``name`` and ``location_type__name``.
        """
        status = extras_models.Status.objects.get(name="Active")
        location_type = dcim_models.LocationType.objects.create(name="Region", nestable=True)
        parent_a = dcim_models.Location.objects.create(name="Parent A", location_type=location_type, status=status)
        parent_b = dcim_models.Location.objects.create(name="Parent B", location_type=location_type, status=status)
        child = dcim_models.Location.objects.create(
            name="Child", location_type=location_type, parent=parent_a, status=status
        )

        class LocationModel(NautobotModel):
            """Test model for testing foreign key functionality identified by multiple fields."""

            _model = dcim_models.Location
            _identifiers = ("name",)
            _attributes = ("parent__name", "parent__location_type__name")

            name: str

            parent__name: str
            parent__location_type__name: str

        location_diffsync = LocationModel(
            name=child.name,
            parent__name=parent_a.name,
            parent__location_type__name=location_type.name,
            pk=child.pk,
        )
        location_diffsync.adapter = MockNautobotAdapter(job=None, sync=None)

        location_diffsync.update(
            attrs={"parent__name": parent_b.name, "parent__location_type__name": location_type.name}
        )
        child.refresh_from_db()

        self.assertEqual(child.parent, parent_b)


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


class BaseModelDefensiveBranchTests(TestCase):
    """Cover the defensive error branches in NautobotModel via targeted ORM-cache failures."""

    def test_create_last_sync_metadata_failure_raises(self):
        """A last-sync metadata write failure during create surfaces as ObjectNotCreated."""
        metadata_type = MetadataType.objects.create(name="Unattached Sync", data_type="datetime")
        adapter = MockNautobotAdapter(job=MagicMock())
        # metadata_type is truthy (enters the branch) but the Tenant content type is not attached.
        adapter.metadata_type = metadata_type
        adapter.metadata_scope_fields = {NautobotTenant: ["name"]}
        with self.assertRaises(ObjectNotCreated):
            NautobotTenant.create(adapter, {"name": "MetaFailTenant"}, {})

    def test_many_to_many_multiple_objects_returned_raises(self):
        """A many-to-many lookup matching multiple objects raises ObjectNotUpdated."""
        tenant = tenancy_models.Tenant.objects.create(name="M2MMulti")
        diffsync_tenant = NautobotTenant(name="M2MMulti", pk=tenant.pk)
        adapter = MockNautobotAdapter(job=MagicMock())
        diffsync_tenant.adapter = adapter
        original = adapter.get_from_orm_cache

        def side_effect(parameters, model_class):
            if model_class is extras_models.Tag:
                raise MultipleObjectsReturned
            return original(parameters, model_class)

        with patch.object(adapter, "get_from_orm_cache", side_effect=side_effect):
            with self.assertRaises(ObjectNotUpdated):
                diffsync_tenant.update({"tags": [{"name": "ambiguous"}]})

    def test_foreign_key_multiple_objects_returned_raises(self):
        """A foreign-key lookup matching multiple objects raises ObjectNotUpdated."""
        tenant = tenancy_models.Tenant.objects.create(name="FKMulti")
        diffsync_tenant = NautobotTenant(name="FKMulti", pk=tenant.pk)
        adapter = MockNautobotAdapter(job=MagicMock())
        diffsync_tenant.adapter = adapter
        original = adapter.get_from_orm_cache

        def side_effect(parameters, model_class):
            if model_class is tenancy_models.TenantGroup:
                raise MultipleObjectsReturned
            return original(parameters, model_class)

        with patch.object(adapter, "get_from_orm_cache", side_effect=side_effect):
            with self.assertRaises(ObjectNotUpdated):
                diffsync_tenant.update({"tenant_group__name": "ambiguous"})

    def test_custom_relationship_source_fk_multiple_objects_returned_raises(self):
        """A SOURCE-side custom-relationship foreign key matching multiple objects raises ObjectNotUpdated."""
        extras_models.Relationship.objects.create(
            label="Test Relationship",
            type=RelationshipTypeChoices.TYPE_ONE_TO_MANY,
            source_type=ContentType.objects.get_for_model(circuits_models.Provider),
            destination_type=ContentType.objects.get_for_model(tenancy_models.Tenant),
        )
        provider = circuits_models.Provider.objects.create(name="SrcMulti")
        diffsync_provider = _ProviderFKSourceModel(name="SrcMulti", pk=provider.pk)
        adapter = _ProviderFKSourceAdapter(job=MagicMock())
        diffsync_provider.adapter = adapter
        original = adapter.get_from_orm_cache

        def side_effect(parameters, model_class):
            # This branch catches the model-specific MultipleObjectsReturned, not the generic one.
            if model_class is tenancy_models.Tenant:
                raise tenancy_models.Tenant.MultipleObjectsReturned
            return original(parameters, model_class)

        with patch.object(adapter, "get_from_orm_cache", side_effect=side_effect):
            with self.assertRaises(ObjectNotUpdated):
                diffsync_provider.update({"tenant__name": "ambiguous"})

    def test_generic_foreign_key_missing_annotation_raises(self):
        """A generic foreign key without app_label/model annotations raises ValueError."""
        foreign_keys = {"assigned_object": {"name": "x", "_model_class": None}}
        with self.assertRaises(ValueError):
            NautobotTenant._lookup_and_set_foreign_keys(  # pylint: disable=protected-access
                foreign_keys, MagicMock(), MockNautobotAdapter(job=MagicMock())
            )
