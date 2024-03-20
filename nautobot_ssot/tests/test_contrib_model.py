"""Tests for contrib.NautobotModel."""

from unittest.mock import MagicMock
from typing import List, Optional

from django.contrib.contenttypes.models import ContentType
from nautobot.circuits import models as circuits_models
from nautobot.core.testing import TestCase
from nautobot.dcim import models as dcim_models
from nautobot.dcim.choices import InterfaceTypeChoices
from nautobot.extras.choices import RelationshipTypeChoices
from nautobot.extras import models as extras_models
from nautobot.tenancy import models as tenancy_models

from nautobot_ssot.contrib import NautobotModel, NautobotAdapter
from nautobot_ssot.tests.contrib_base_classes import (
    TenantModelCustomRelationship,
    ProviderModelCustomRelationship,
    TestCaseWithDeviceData,
    NautobotTenant,
    TagModel,
    TagDict,
)
from nautobot_ssot.tests.test_contrib_adapter import (
    CustomRelationShipTestAdapterSource,
    CustomRelationShipTestAdapterDestination,
)


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
