"""Tests for telling an IP Fabric sync which object types it may not create.

The integration creates supporting objects on demand. Strictness withholds that, so what these tests
pin is what the sync does when the object it would have created is absent: for each type, whether the
record that needed it is skipped, synced without it, or synced with the part it could resolve.

The behavioural cases run against the real database rather than against mocks of the helpers that
talk to it, as `test_supporting_object_scope.py` does for the scope controls.
"""

import unittest.mock

from nautobot.apps.testing import TestCase
from nautobot.dcim.models import Device, DeviceType, Location, Manufacturer, Platform, VirtualChassis
from nautobot.extras.models import Role, Status
from parameterized import parameterized

from nautobot_ssot.integrations.ipfabric import strict_mode
from nautobot_ssot.integrations.ipfabric.diffsync.adapters_shared import DiffSyncModelAdapters
from nautobot_ssot.integrations.ipfabric.strict_mode import STRICT_OBJECTS, StrictObjects
from nautobot_ssot.tests.ipfabric.supporting_objects import (
    KNOWN_STACK,
    UNKNOWN_LOCATION,
    UNKNOWN_MODEL,
    UNKNOWN_PLATFORM,
    UNKNOWN_ROLE,
    UNKNOWN_STACK,
    UNKNOWN_VENDOR,
    SupportingObjectTestCase,
    scope_without,
)


class StrictObjectsTestCase(TestCase):
    """Test resolving the selection into the object the adapters read."""

    def test_a_selected_type_is_strict(self):
        strict = StrictObjects(("locations", "roles"))

        self.assertTrue(strict.locations)
        self.assertTrue(strict.roles)

    def test_an_unselected_type_is_not_strict(self):
        self.assertFalse(StrictObjects(("locations",)).platforms)

    def test_an_unknown_key_is_ignored(self):
        """A schedule naming a type this version dropped still resolves, rather than raising."""
        self.assertEqual(list(StrictObjects(("locations", "gone"))), ["locations"])

    def test_an_unregistered_attribute_still_raises(self):
        with self.assertRaises(AttributeError):
            getattr(StrictObjects(()), "spelled_wrong")

    def test_iteration_follows_registration_order(self):
        """Deterministic, so the log line naming them does not reorder between runs."""
        selected = ("ip_addresses", "locations", "statuses")

        self.assertEqual(list(StrictObjects(selected)), ["locations", "statuses", "ip_addresses"])

    def test_a_missing_field_falls_back_to_the_defaults(self):
        """A run through the API, or a schedule made before the field existed, behaves as the form."""
        strict = StrictObjects.from_job_kwargs({})

        self.assertEqual(list(strict), list(strict_mode.default_keys()))

    def test_an_empty_selection_is_honoured(self):
        """Empty is a choice, not an omission, so it must not read as the defaults."""
        strict = StrictObjects.from_job_kwargs({strict_mode.FIELD_NAME: []})

        self.assertEqual(list(strict), [])

    def test_only_ip_addresses_is_strict_by_default(self):
        """Every other type defaults to creating, so that no existing sync changes behaviour."""
        self.assertEqual(strict_mode.default_keys(), ("ip_addresses",))

    def test_the_form_field_offers_every_registered_type(self):
        field = strict_mode.form_field()

        self.assertEqual([key for key, _label in field.field_attrs["choices"]], [o.key for o in STRICT_OBJECTS])

    def test_a_selection_the_scope_has_already_made_redundant_is_reported(self):
        """Both controls stop creation, so the selection is not the reason nothing was created."""
        scope = scope_without("roles")

        messages = StrictObjects(("roles",)).explanations(scope)

        self.assertEqual(len(messages), 1)
        self.assertIn("roles", messages[0])

    def test_a_selection_the_scope_has_not_made_redundant_is_not_reported(self):
        self.assertEqual(StrictObjects(("roles",)).explanations(scope_without()), [])

    def test_a_type_with_no_scope_toggle_is_never_reported_as_redundant(self):
        """Statuses and Virtual Chassis cannot be deselected, so the scope never covers them."""
        self.assertEqual(StrictObjects(("statuses", "virtual_chassis")).explanations(scope_without()), [])


class MayCreateTestCase(TestCase):
    """Test how the two controls layer: the scope decides whether, strictness whether to trust."""

    def _adapter(self, scope=None, strict=()):
        adapter = DiffSyncModelAdapters(
            scope=scope if scope is not None else scope_without(), strict=StrictObjects(strict)
        )
        adapter.job = unittest.mock.MagicMock()
        return adapter

    def test_in_scope_and_not_strict_may_create(self):
        self.assertTrue(self._adapter().may_create("roles"))

    def test_strict_may_not_create(self):
        self.assertFalse(self._adapter(strict=("roles",)).may_create("roles"))

    def test_out_of_scope_may_not_create(self):
        """A type this run does not sync is one it has no business introducing."""
        scope = scope_without("roles")

        self.assertFalse(self._adapter(scope=scope).may_create("roles"))

    def test_strictness_adds_nothing_to_a_type_out_of_scope(self):
        """Strictness checks what would have been written, and out of scope nothing would be."""
        scope = scope_without("roles")

        self.assertEqual(
            self._adapter(scope=scope).may_create("roles"),
            self._adapter(scope=scope, strict=("roles",)).may_create("roles"),
        )

    def test_strictness_does_not_bring_a_type_into_scope(self):
        """Selecting a type is a check on what is synced, never a reason to start syncing it."""
        adapter = self._adapter(scope=scope_without("vlans"), strict=("vlans",))

        self.assertFalse(adapter.may_create("vlans"))

    def test_a_type_with_no_scope_toggle_is_governed_by_strictness_alone(self):
        self.assertTrue(self._adapter().may_create("statuses"))
        self.assertFalse(self._adapter(strict=("statuses",)).may_create("statuses"))


class StrictSupportingObjectTestCase(SupportingObjectTestCase):
    """Test what a sync does for a supporting object type it is strict about."""

    def be_strict_about(self, *keys):
        """Select the named object types as ones this run may not create."""
        self.adapter.strict = StrictObjects(keys)

    def test_nothing_strict_creates_what_is_missing(self):
        """The default keeps the existing behaviour of creating supporting objects as needed."""
        self.create_device(vendor=UNKNOWN_VENDOR, model=UNKNOWN_MODEL, role=UNKNOWN_ROLE, platform=UNKNOWN_PLATFORM)

        self.assertTrue(Manufacturer.objects.filter(name=UNKNOWN_VENDOR).exists())
        self.assertTrue(DeviceType.objects.filter(model=UNKNOWN_MODEL).exists())
        self.assertTrue(Role.objects.filter(_custom_field_data__ipfabric_type=UNKNOWN_ROLE).exists())
        self.assertTrue(Platform.objects.filter(name=UNKNOWN_PLATFORM).exists())
        self.assertTrue(Device.objects.filter(name="dev1").exists())

    # --- strict, supporting object present ---------------------------------

    def test_existing_supporting_objects_are_reused(self):
        """Strictness does not stop Devices syncing; it stops the sync adding to the catalogue."""
        self.be_strict_about("manufacturers", "device_types", "roles", "platforms")

        self.create_device()

        device = Device.objects.get(name="dev1")
        self.assertEqual(device.device_type, self.device_type)
        self.assertEqual(device.role, self.role)
        self.assertEqual(device.platform, self.platform)

    def test_no_supporting_object_is_created_when_all_are_present(self):
        self.be_strict_about("manufacturers", "device_types", "roles", "platforms")
        before = (Manufacturer.objects.count(), DeviceType.objects.count(), Role.objects.count())

        self.create_device()

        self.assertEqual(before, (Manufacturer.objects.count(), DeviceType.objects.count(), Role.objects.count()))

    # --- strict, supporting object absent ----------------------------------

    @parameterized.expand(
        [
            ("device_types", {"model": UNKNOWN_MODEL}, "DeviceType"),
            ("roles", {"role": UNKNOWN_ROLE}, "Role"),
            ("locations", {"location_name": UNKNOWN_LOCATION}, "Location"),
        ]
    )
    def test_a_missing_required_object_skips_the_device(self, key, overrides, reported):
        """Nautobot requires each of these, so the Device cannot be written without it."""
        self.be_strict_about(key)

        self.create_device(**overrides)

        self.assertFalse(Device.objects.filter(name="dev1").exists())
        self.assert_warned(reported)

    def test_a_missing_device_type_is_not_created(self):
        self.be_strict_about("device_types")

        self.create_device(model=UNKNOWN_MODEL)

        self.assertFalse(DeviceType.objects.filter(model=UNKNOWN_MODEL).exists())

    def test_a_missing_manufacturer_is_not_created_to_hold_a_new_model(self):
        """A sync told not to add vendors must not add one in order to add a model."""
        self.be_strict_about("manufacturers")

        self.create_device(vendor=UNKNOWN_VENDOR, model=UNKNOWN_MODEL)

        self.assertFalse(Manufacturer.objects.filter(name=UNKNOWN_VENDOR).exists())
        self.assertFalse(DeviceType.objects.filter(model=UNKNOWN_MODEL).exists())

    def test_a_missing_role_is_not_created(self):
        self.be_strict_about("roles")

        self.create_device(role=UNKNOWN_ROLE)

        self.assertFalse(Role.objects.filter(_custom_field_data__ipfabric_type=UNKNOWN_ROLE).exists())

    def test_a_missing_platform_syncs_the_device_without_one(self):
        """Platform is optional in Nautobot, so a missing one costs the Platform, not the Device."""
        self.be_strict_about("platforms")

        self.create_device(platform=UNKNOWN_PLATFORM)

        self.assertFalse(Platform.objects.filter(name=UNKNOWN_PLATFORM).exists())
        self.assertIsNone(Device.objects.get(name="dev1").platform)

    def test_a_missing_location_is_not_created(self):
        self.be_strict_about("locations")

        self.create_device(location_name=UNKNOWN_LOCATION)

        self.assertFalse(Location.objects.filter(name=UNKNOWN_LOCATION).exists())

    # --- statuses ----------------------------------------------------------

    def test_a_missing_status_is_not_created(self):
        self.be_strict_about("statuses")

        self.create_device(status="No-Such-Status")

        self.assertFalse(Status.objects.filter(name="No-Such-Status").exists())

    def test_an_existing_status_is_still_used(self):
        self.be_strict_about("statuses")

        self.create_device()

        self.assertEqual(Device.objects.get(name="dev1").status, self.active_status)

    # --- virtual chassis ---------------------------------------------------

    def test_a_missing_virtual_chassis_is_not_created(self):
        """Stack membership goes unrecorded rather than a Virtual Chassis being introduced for it."""
        self.be_strict_about("virtual_chassis")

        self.create_device(vc_name=UNKNOWN_STACK, vc_position=1, vc_priority=1)

        self.assertFalse(VirtualChassis.objects.filter(name=UNKNOWN_STACK).exists())

    def test_an_existing_virtual_chassis_is_still_joined(self):
        self.be_strict_about("virtual_chassis")

        self.create_device(vc_name=KNOWN_STACK, vc_position=1, vc_priority=1)

        self.assertEqual(Device.objects.get(name="dev1").virtual_chassis.name, KNOWN_STACK)
