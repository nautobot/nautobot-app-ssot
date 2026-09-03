"""Tests for taking Manufacturers, Device Types, Roles and Platforms out of an IP Fabric sync's scope.

These four are not part of the object tree. They are created as a side effect of syncing a Device,
which is what makes them worth their own controls: an estate where a hardware catalogue owns Device
Types, or where roles are assigned by another process, does not want a discovery sync inventing them.

Deselecting one therefore does not stop Devices syncing. It changes a get-or-create into a lookup, so
what the sync does when the supporting object is absent is the behaviour these tests pin, against the
real database rather than against mocks of the helpers that talk to it.
"""

from django.contrib.contenttypes.models import ContentType
from nautobot.dcim.models import Device, DeviceType, Manufacturer, Platform
from nautobot.extras.models import Role

from nautobot_ssot.tests.ipfabric.supporting_objects import (
    UNKNOWN_MODEL,
    UNKNOWN_PLATFORM,
    UNKNOWN_ROLE,
    UNKNOWN_VENDOR,
    SupportingObjectTestCase,
    scope_without,
)


class SupportingObjectScopeTestCase(SupportingObjectTestCase):
    """Test what a sync does for a supporting object type taken out of the sync scope."""

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
