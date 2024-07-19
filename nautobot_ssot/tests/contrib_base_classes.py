"""Base classes for contrib testing."""

from typing import Optional, List
from unittest import skip
from unittest.mock import MagicMock
from diffsync.exceptions import ObjectNotCreated, ObjectNotUpdated, ObjectNotDeleted
from django.contrib.contenttypes.models import ContentType
import nautobot.circuits.models as circuits_models
from nautobot.dcim.choices import InterfaceTypeChoices
import nautobot.extras.models as extras_models
import nautobot.dcim.models as dcim_models
import nautobot.ipam.models as ipam_models
import nautobot.tenancy.models as tenancy_models
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
        cls.status_active = extras_models.Status.objects.get(name="Active")
        cls.device_role = extras_models.Role.objects.create(name="Switch")
        cls.device_role.content_types.set([ContentType.objects.get_for_model(dcim_models.Device)])
        cls.manufacturer = dcim_models.Manufacturer.objects.create(name="Generic Inc.")
        cls.device_type = dcim_models.DeviceType.objects.create(model="Generic Switch", manufacturer=cls.manufacturer)
        cls.location_type, created = dcim_models.LocationType.objects.get_or_create(name="Site")
        if created:
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
        diffsync_tenant.diffsync = NautobotAdapter(job=None, sync=None)
        diffsync_tenant.update(attrs={"tenant_group__name": None})

        tenant.refresh_from_db()
        self.assertEqual(None, tenant.tenant_group, "Foreign key update to None through 'NautobotModel' does not work.")

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
