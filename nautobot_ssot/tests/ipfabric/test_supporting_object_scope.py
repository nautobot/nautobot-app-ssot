"""Tests for taking Manufacturers, Device Types, Roles and Platforms out of an IP Fabric sync's scope.

These four are not part of the object tree. They are created as a side effect of syncing a Device,
which is what makes them worth their own controls: an estate where a hardware catalogue owns Device
Types, or where roles are assigned by another process, does not want a discovery sync inventing them.

Deselecting one therefore does not stop Devices syncing. It changes a get-or-create into a lookup, so
what the sync does when the supporting object is absent is the behaviour these tests pin, against the
real database rather than against mocks of the helpers that talk to it.
"""

import unittest.mock

from django.contrib.contenttypes.models import ContentType
from nautobot.apps.testing import TestCase
from nautobot.dcim.models import Device, DeviceType, Location, LocationType, Manufacturer, Platform
from nautobot.extras.choices import CustomFieldTypeChoices
from nautobot.extras.management import populate_status_choices
from nautobot.extras.models import CustomField, Role, Status

from nautobot_ssot.integrations.ipfabric.diffsync.adapters_shared import DiffSyncModelAdapters
from nautobot_ssot.integrations.ipfabric.diffsync.diffsync_models import Device as DeviceModel
from nautobot_ssot.integrations.ipfabric.sync_scope import SYNCABLE_OBJECTS, SyncScope
from nautobot_ssot.integrations.ipfabric.utilities.utils import job_scoped_cache

KNOWN_VENDOR = "known-vendor"
KNOWN_MODEL = "known-model"
KNOWN_ROLE = "known-role"
KNOWN_PLATFORM = "known-platform"

UNKNOWN_VENDOR = "unknown-vendor"
UNKNOWN_MODEL = "unknown-model"
UNKNOWN_ROLE = "unknown-role"
UNKNOWN_PLATFORM = "unknown-platform"


def scope_without(*keys):
    """Return a scope with every object type selected except the named ones."""
    return SyncScope(syncable.key for syncable in SYNCABLE_OBJECTS if syncable.key not in keys)


class SupportingObjectScopeTestCase(TestCase):
    """Create Devices against a Nautobot that holds some supporting objects and not others."""

    def setUp(self):
        # Helpers memoize real ORM objects, which would outlive this test's transaction.
        job_scoped_cache.clear_all()
        self.addCleanup(job_scoped_cache.clear_all)

        populate_status_choices()
        self.active_status = Status.objects.get(name="Active")
        device_ct = ContentType.objects.get_for_model(Device)

        self.manufacturer = Manufacturer.objects.create(name=KNOWN_VENDOR)
        self.device_type = DeviceType.objects.create(model=KNOWN_MODEL, manufacturer=self.manufacturer)
        self.platform = Platform.objects.create(name=KNOWN_PLATFORM, manufacturer=self.manufacturer)

        # `get_or_create_device_role_object` matches on this custom field rather than the name.
        role_cf, _ = CustomField.objects.get_or_create(
            type=CustomFieldTypeChoices.TYPE_TEXT,
            key="ipfabric_type",
            defaults={"label": "IPFabric Type"},
        )
        role_cf.content_types.add(ContentType.objects.get_for_model(Role))
        self.role = Role.objects.create(name=KNOWN_ROLE)
        self.role.content_types.add(device_ct)
        self.role.cf["ipfabric_type"] = KNOWN_ROLE
        self.role.validated_save()

        site_type, _ = LocationType.objects.get_or_create(name="Site")
        site_type.content_types.add(device_ct)
        self.location = Location.objects.create(name="site1", location_type=site_type, status=self.active_status)

        # A real Adapter, since `DiffSyncModel.create` validates the type; only the job is mocked.
        self.adapter = DiffSyncModelAdapters(scope=SyncScope(syncable.key for syncable in SYNCABLE_OBJECTS))
        self.adapter.job = unittest.mock.MagicMock()

    def create_device(self, name="dev1", **overrides):
        """Run `Device.create` for a Device whose supporting objects default to the known ones."""
        attrs = {
            "location_name": self.location.name,
            "model": KNOWN_MODEL,
            "vendor": KNOWN_VENDOR,
            "role": KNOWN_ROLE,
            "status": "Active",
            "platform": KNOWN_PLATFORM,
            "serial_number": "abc123",
        }
        attrs.update(overrides)
        return DeviceModel.create(self.adapter, ids={"name": name}, attrs=attrs)

    def assert_warned(self, fragment):
        """Assert the job logged a warning containing the given text."""
        logged = [str(call) for call in self.adapter.job.logger.warning.call_args_list]
        self.assertTrue(
            any(fragment in line for line in logged), f"Expected a warning containing {fragment!r}: {logged}"
        )

    # --- in scope: the behaviour that must not change ----------------------

    def test_everything_in_scope_creates_what_is_missing(self):
        """The default scope keeps the existing behaviour of creating supporting objects as needed."""
        self.create_device(vendor=UNKNOWN_VENDOR, model=UNKNOWN_MODEL, role=UNKNOWN_ROLE, platform=UNKNOWN_PLATFORM)

        self.assertTrue(Manufacturer.objects.filter(name=UNKNOWN_VENDOR).exists())
        self.assertTrue(DeviceType.objects.filter(model=UNKNOWN_MODEL).exists())
        self.assertTrue(Role.objects.filter(_custom_field_data__ipfabric_type=UNKNOWN_ROLE).exists())
        self.assertTrue(Platform.objects.filter(name=UNKNOWN_PLATFORM).exists())
        self.assertTrue(Device.objects.filter(name="dev1").exists())

    # --- out of scope, supporting object present ---------------------------

    def test_existing_supporting_objects_are_reused_out_of_scope(self):
        """Deselecting all four still syncs a Device whose supporting objects Nautobot already holds."""
        self.adapter.scope = scope_without("manufacturers", "device_types", "roles", "platforms")

        self.create_device()

        device = Device.objects.get(name="dev1")
        self.assertEqual(device.device_type, self.device_type)
        self.assertEqual(device.role, self.role)
        self.assertEqual(device.platform, self.platform)

    def test_no_supporting_objects_are_created_out_of_scope(self):
        """Nothing is added to the four catalogues, which is the point of deselecting them."""
        self.adapter.scope = scope_without("manufacturers", "device_types", "roles", "platforms")
        before = (
            Manufacturer.objects.count(),
            DeviceType.objects.count(),
            Role.objects.count(),
            Platform.objects.count(),
        )

        self.create_device()

        self.assertEqual(
            before,
            (
                Manufacturer.objects.count(),
                DeviceType.objects.count(),
                Role.objects.count(),
                Platform.objects.count(),
            ),
        )

    # --- out of scope, supporting object absent ----------------------------

    def test_device_type_out_of_scope_skips_a_device_with_an_unknown_model(self):
        """Nautobot requires a DeviceType, so a Device whose model is not catalogued cannot be made."""
        self.adapter.scope = scope_without("device_types")

        self.create_device(model=UNKNOWN_MODEL)

        self.assertFalse(DeviceType.objects.filter(model=UNKNOWN_MODEL).exists())
        self.assertFalse(Device.objects.filter(name="dev1").exists())
        self.assert_warned("DeviceType")

    def test_manufacturer_out_of_scope_blocks_creating_a_device_type(self):
        """A sync told not to add vendors must not add one in order to add a model."""
        self.adapter.scope = scope_without("manufacturers")

        self.create_device(vendor=UNKNOWN_VENDOR, model=UNKNOWN_MODEL)

        self.assertFalse(Manufacturer.objects.filter(name=UNKNOWN_VENDOR).exists())
        self.assertFalse(DeviceType.objects.filter(model=UNKNOWN_MODEL).exists())
        self.assert_warned(f"no Manufacturer named {UNKNOWN_VENDOR} could be resolved")

    def test_manufacturer_out_of_scope_still_allows_a_known_vendor(self):
        """The restriction is on adding vendors, not on using the ones Nautobot already holds."""
        self.adapter.scope = scope_without("manufacturers")

        self.create_device(model=UNKNOWN_MODEL)

        created = DeviceType.objects.get(model=UNKNOWN_MODEL)
        self.assertEqual(created.manufacturer, self.manufacturer)
        self.assertTrue(Device.objects.filter(name="dev1").exists())

    def test_roles_out_of_scope_skips_a_device_with_an_unknown_role(self):
        """Nautobot requires a Role, so a Device whose role is not defined cannot be made."""
        self.adapter.scope = scope_without("roles")

        self.create_device(role=UNKNOWN_ROLE)

        self.assertFalse(Role.objects.filter(name=UNKNOWN_ROLE).exists())
        self.assertFalse(Device.objects.filter(name="dev1").exists())
        self.assert_warned("to get or create a Role")

    def test_roles_out_of_scope_matches_a_role_by_name(self):
        """Out of scope the Role comes from a system that does not set the IP Fabric custom field."""
        other_role = Role.objects.create(name="externally-owned")
        other_role.content_types.add(ContentType.objects.get_for_model(Device))
        self.adapter.scope = scope_without("roles")

        self.create_device(role="externally-owned")

        self.assertEqual(Device.objects.get(name="dev1").role, other_role)

    def test_roles_out_of_scope_leaves_the_custom_field_alone(self):
        """Stamping `ipfabric_type` onto a Role another system owns is what deselecting Roles refuses."""
        other_role = Role.objects.create(name="externally-owned")
        other_role.content_types.add(ContentType.objects.get_for_model(Device))
        self.adapter.scope = scope_without("roles")

        self.create_device(role="externally-owned")

        other_role.refresh_from_db()
        self.assertIsNone(other_role.cf.get("ipfabric_type"))

    def test_platforms_out_of_scope_syncs_the_device_without_one(self):
        """Platform is optional on a Device, so an unknown one costs the Platform, not the Device."""
        self.adapter.scope = scope_without("platforms")

        self.create_device(platform=UNKNOWN_PLATFORM)

        self.assertFalse(Platform.objects.filter(name=UNKNOWN_PLATFORM).exists())
        device = Device.objects.get(name="dev1")
        self.assertIsNone(device.platform)
        self.assert_warned("will not have a Platform assigned")

    def test_platforms_out_of_scope_matches_on_name_alone(self):
        """The system that owns a Platform decides its Manufacturer, so the match cannot require one."""
        other_manufacturer = Manufacturer.objects.create(name="other-vendor")
        shared = Platform.objects.create(name="shared-platform", manufacturer=other_manufacturer)
        self.adapter.scope = scope_without("platforms")

        self.create_device(platform="shared-platform")

        self.assertEqual(Device.objects.get(name="dev1").platform, shared)
