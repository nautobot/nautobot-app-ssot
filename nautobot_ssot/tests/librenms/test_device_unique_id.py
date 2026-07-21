"""Tests for tenant-scoped LibreNMS device_id keying: renames, tenant isolation, and backfill."""

from unittest.mock import MagicMock

from diffsync import Adapter
from django.contrib.contenttypes.models import ContentType
from nautobot.apps.testing import TestCase
from nautobot.dcim.models import Device as ORMDevice
from nautobot.dcim.models import DeviceType, LocationType, Manufacturer
from nautobot.dcim.models import Location as ORMLocation
from nautobot.extras.models import Role, Status

from nautobot_ssot.integrations.librenms.diffsync.models.base import Device
from nautobot_ssot.integrations.librenms.utils import (
    backfill_librenms_device_ids,
    build_device_unique_id,
)


class TestBuildDeviceUniqueId(TestCase):
    """Unit tests for build_device_unique_id."""

    def test_uses_device_id_when_present(self):
        """A device_id, when known, is the sole basis for the key (besides tenant)."""
        self.assertEqual(build_device_unique_id("TenantA", 42, "old-name"), "TenantA::id::42")

    def test_rename_keeps_same_unique_id(self):
        """The same device_id must produce the same key even if the name changes."""
        before = build_device_unique_id("TenantA", 42, "old-name")
        after = build_device_unique_id("TenantA", 42, "new-name")
        self.assertEqual(before, after)

    def test_falls_back_to_name_when_no_device_id(self):
        """With no device_id known yet, the key falls back to a tenant-scoped name."""
        self.assertEqual(build_device_unique_id("TenantA", None, "some-device"), "TenantA::name::some-device")

    def test_defaults_tenant_to_global(self):
        """No tenant selected falls back to the GLOBAL namespace."""
        self.assertEqual(build_device_unique_id(None, 5, "dev"), "GLOBAL::id::5")

    def test_no_device_id_devices_do_not_collide_across_names(self):
        """Two different devices with no device_id must not share a key."""
        first = build_device_unique_id("TenantA", None, "device-one")
        second = build_device_unique_id("TenantA", None, "device-two")
        self.assertNotEqual(first, second)

    def test_same_device_id_different_tenants_do_not_collide(self):
        """Two LibreNMS instances with overlapping device_id numbering stay isolated per tenant."""
        first = build_device_unique_id("TenantA", 1, "dev")
        second = build_device_unique_id("TenantB", 1, "dev")
        self.assertNotEqual(first, second)


class _DeviceOnlyAdapter(Adapter):
    """Minimal DiffSync adapter exposing only the Device model, for exercising diff/add in isolation."""

    device = Device
    top_level = ["device"]


def _make_device(unique_id, name, device_id, tenant):
    return Device(
        unique_id=unique_id,
        name=name,
        device_id=device_id,
        location="City Hall",
        status="Active",
        device_type="Generic Device",
        manufacturer="Generic",
        tenant=tenant,
        system_of_record="LibreNMS",
    )


class TestDeviceRenameDoesNotRecreate(TestCase):
    """Confirm that a LibreNMS-side rename produces an update, not a delete+create, in the diff."""

    def test_rename_with_stable_device_id_is_an_update(self):
        dest_adapter = _DeviceOnlyAdapter()
        dest_adapter.add(_make_device(build_device_unique_id("GLOBAL", 42, "OLD-NAME"), "OLD-NAME", 42, None))

        source_adapter = _DeviceOnlyAdapter()
        source_adapter.add(_make_device(build_device_unique_id("GLOBAL", 42, "NEW-NAME"), "NEW-NAME", 42, None))

        diff = source_adapter.diff_to(dest_adapter)
        summary = diff.summary()

        self.assertEqual(summary.get("create", 0), 0)
        self.assertEqual(summary.get("delete", 0), 0)
        self.assertEqual(summary.get("update", 0), 1)


class TestTenantRenameDoesNotBreakMatching(TestCase):
    """Confirm a Tenant rename never causes a stale-key mismatch (false create/delete)."""

    def test_diff_after_tenant_rename_is_clean_match_not_create_delete(self):
        """Both sides recompute the tenant name live, so a rename shifts the key symmetrically."""
        dest_adapter = _DeviceOnlyAdapter()
        dest_adapter.add(_make_device(build_device_unique_id("New Tenant", 42, "dev"), "dev", 42, "New Tenant"))

        source_adapter = _DeviceOnlyAdapter()
        source_adapter.add(_make_device(build_device_unique_id("New Tenant", 42, "dev"), "dev", 42, "New Tenant"))

        diff = source_adapter.diff_to(dest_adapter)
        summary = diff.summary()

        self.assertEqual(summary.get("create", 0), 0)
        self.assertEqual(summary.get("delete", 0), 0)

    def test_rename_changes_the_key_across_runs(self):
        """A renamed tenant does produce a different key than before the rename (sanity check)."""
        before_rename = build_device_unique_id("Old Tenant", 42, "dev")
        after_rename = build_device_unique_id("New Tenant", 42, "dev")
        self.assertNotEqual(before_rename, after_rename)


class TestTenantScopedDeviceKeyNoCollision(TestCase):
    """Confirm two devices sharing a device_id under different tenants can coexist in one adapter."""

    def test_same_device_id_different_tenant_added_without_collision(self):
        adapter = _DeviceOnlyAdapter()

        device_a = _make_device(build_device_unique_id("TenantA", 7, "dev-a"), "dev-a", 7, "TenantA")
        device_b = _make_device(build_device_unique_id("TenantB", 7, "dev-b"), "dev-b", 7, "TenantB")

        adapter.add(device_a)
        adapter.add(device_b)

        self.assertEqual(len(list(adapter.get_all("device"))), 2)


class TestBackfillLibrenmsDeviceIds(TestCase):
    """Confirm the automatic backfill stamps librenms_device_id onto devices synced under the old scheme."""

    databases = ("default", "job_logs")

    def setUp(self):
        """Set up Nautobot Devices representing the old name-keyed and already-tagged states."""
        super().setUp()
        self.active_status, _ = Status.objects.get_or_create(name="Active")
        self.active_status.content_types.add(ContentType.objects.get_for_model(ORMDevice))

        self.site_type, _ = LocationType.objects.get_or_create(name="Site")
        self.site_type.content_types.add(ContentType.objects.get_for_model(ORMDevice))

        self.location = ORMLocation.objects.create(
            name="Test Site", location_type=self.site_type, status=self.active_status
        )

        manufacturer, _ = Manufacturer.objects.get_or_create(name="Generic")
        device_type, _ = DeviceType.objects.get_or_create(model="Test Device Type", manufacturer=manufacturer)
        role, _ = Role.objects.get_or_create(name="Test Role")
        role.content_types.add(ContentType.objects.get_for_model(ORMDevice))

        self.device_no_id = ORMDevice.objects.create(
            name="legacy-device",
            device_type=device_type,
            status=self.active_status,
            role=role,
            location=self.location,
        )
        self.device_with_id = ORMDevice.objects.create(
            name="already-tagged-device",
            device_type=device_type,
            status=self.active_status,
            role=role,
            location=self.location,
        )
        self.device_with_id.custom_field_data["librenms_device_id"] = 99
        self.device_with_id.validated_save()

        self.job = MagicMock()

    def test_backfill_matches_by_hostname_and_stamps_device_id(self):
        """A device synced under the old name-only key gets its librenms_device_id stamped by hostname match."""
        hostname_to_device_id = {"legacy-device": 5, "already-tagged-device": 999}

        matched = backfill_librenms_device_ids(
            ORMDevice.objects.filter(pk__in=[self.device_no_id.pk, self.device_with_id.pk]),
            hostname_to_device_id,
            self.job,
        )

        self.assertEqual(matched, 1)

        self.device_no_id.refresh_from_db()
        self.assertEqual(self.device_no_id.custom_field_data.get("librenms_device_id"), 5)

        # Idempotent: a device that already has the custom field set is left untouched.
        self.device_with_id.refresh_from_db()
        self.assertEqual(self.device_with_id.custom_field_data.get("librenms_device_id"), 99)

    def test_backfill_no_op_for_unmatched_hostname(self):
        """A device with no matching LibreNMS hostname is left alone."""
        matched = backfill_librenms_device_ids(
            ORMDevice.objects.filter(pk=self.device_no_id.pk),
            {},
            self.job,
        )

        self.assertEqual(matched, 0)
        self.device_no_id.refresh_from_db()
        self.assertFalse(self.device_no_id.custom_field_data.get("librenms_device_id"))
