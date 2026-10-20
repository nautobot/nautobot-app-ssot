"""Tests for recording the OS version IP Fabric reports for each Device as a Nautobot Software Version."""

from collections import defaultdict
from unittest.mock import MagicMock, patch

from django.apps import apps as global_apps
from django.core.exceptions import ValidationError
from ipfabric.models.device import Device as IPFabricDevice
from nautobot.dcim.models import Device as NautobotDevice
from nautobot.dcim.models import Platform, SoftwareVersion

from nautobot_ssot.integrations.ipfabric.diffsync.adapter_nautobot import NautobotDiffSync
from nautobot_ssot.integrations.ipfabric.diffsync.diffsync_models import Device as DeviceModel
from nautobot_ssot.integrations.ipfabric.signals import nautobot_database_ready_callback
from nautobot_ssot.integrations.ipfabric.sync_scope import SyncScope
from nautobot_ssot.integrations.ipfabric.utilities import nbutils
from nautobot_ssot.tests.ipfabric.job_log import job_log_text
from nautobot_ssot.tests.ipfabric.supporting_objects import (
    KNOWN_PLATFORM,
    KNOWN_VENDOR,
    SupportingObjectTestCase,
    scope_without,
)
from nautobot_ssot.tests.ipfabric.test_ipfabric_adapter import (
    DEVICE_INVENTORY_FIXTURE,
    build_adapter,
    mock_ipfabric_client,
)


class TestWhichVersionIsLoaded(SupportingObjectTestCase):
    """What the IP Fabric adapter reports for a Device's software version."""

    def loaded(self, sync_software_versions=True, **overrides):
        """Return `(devices keyed by name, the adapter)` over the fixtures, with overrides applied."""
        client = mock_ipfabric_client()
        client.devices.by_site = defaultdict(list)
        for record in DEVICE_INVENTORY_FIXTURE:
            record = dict(record, **overrides)
            client.devices.by_site[record["siteName"]].append(IPFabricDevice(**record))  # pylint: disable=no-member
        adapter = build_adapter(client=client, sync_software_versions=sync_software_versions)
        return {device.name: device for device in adapter.get_all("device")}, adapter

    def test_the_reported_version_is_loaded(self):
        devices, adapter = self.loaded()
        self.assertEqual("18.2R1.9", devices["nyc-rtr-01"].software_version)
        self.assertEqual(adapter.devices_without_a_software_version, set())

    def test_every_member_of_a_stack_reports_the_stack_version(self):
        devices, _ = self.loaded()
        members = [device for device in devices.values() if device.vc_name == "stack"]
        self.assertGreater(len(members), 1)
        self.assertEqual({device.software_version for device in members}, {"17.1.1"})

    def test_a_device_reporting_no_version_is_registered_as_absent(self):
        devices, adapter = self.loaded(version=None)
        self.assertIsNone(devices["nyc-rtr-01"].software_version)
        self.assertIn("nyc-rtr-01", adapter.devices_without_a_software_version)

    def test_a_device_with_no_family_has_no_platform_to_file_a_version_under(self):
        """Cloud devices report a version but no family, and a Software Version belongs to a Platform."""
        devices, adapter = self.loaded(family=None)
        self.assertIsNone(devices["nyc-rtr-01"].software_version)
        self.assertIn("nyc-rtr-01", adapter.devices_without_a_software_version)

    def test_out_of_scope_nothing_is_reported_or_registered(self):
        devices, adapter = self.loaded(sync_software_versions=False)
        self.assertIsNone(devices["nyc-rtr-01"].software_version)
        self.assertEqual(adapter.devices_without_a_software_version, set())

    def test_off_unless_selected(self):
        self.assertFalse(SyncScope.from_job_kwargs({}).software_versions)

    def test_the_platform_and_version_lookups_are_cached_for_the_run(self):
        """Every Device resolves both, and most of them resolve the same few."""
        for lookup in (nbutils.get_or_create_platform_object, nbutils.get_or_create_software_version):
            with self.subTest(lookup=lookup.__name__):
                self.assertTrue(hasattr(lookup, "cache_info"), f"{lookup.__name__} is not cached")


def prepare(test):
    """Make the custom fields a created version is stamped with, and scope the run to versions."""
    nautobot_database_ready_callback(sender=None, apps=global_apps)
    test.adapter.scope = scope_without()


def written(test, name="dev1", **overrides):
    """Create a Device through the sync's own model and return the Nautobot record."""
    test.create_device(name=name, **overrides)
    return NautobotDevice.objects.get(name=name)


class TestWritingTheVersion(SupportingObjectTestCase):
    """What reaches Nautobot when the sync creates or updates a Device."""

    def setUp(self):
        super().setUp()
        prepare(self)

    def written(self, name="dev1", **overrides):
        """Create a Device through the sync's own model and return the Nautobot record."""
        return written(self, name, **overrides)

    def test_a_new_device_gets_its_version_under_its_platform(self):
        device = self.written(software_version="18.2R1.9")
        self.assertEqual(device.software_version.version, "18.2R1.9")
        self.assertEqual(device.software_version.platform, self.platform)
        self.assertEqual(device.software_version.status.name, "Active")

    def test_a_created_version_is_marked_as_synced(self):
        version = self.written(software_version="18.2R1.9").software_version
        self.assertTrue(version.tags.filter(name="SSoT Synced from IPFabric").exists())
        self.assertEqual(version.cf["system_of_record"], "IPFabric")

    def test_a_version_nautobot_holds_is_used_rather_than_duplicated(self):
        existing = SoftwareVersion.objects.create(platform=self.platform, version="18.2R1.9", status=self.active_status)
        self.written("dev1", software_version="18.2R1.9")
        self.written("dev2", software_version="18.2R1.9")
        self.assertEqual(SoftwareVersion.objects.count(), 1)
        self.assertEqual(NautobotDevice.objects.get(name="dev2").software_version, existing)
        self.assertFalse(existing.tags.exists())

    def test_a_device_with_no_platform_is_written_without_a_version(self):
        device = self.written(platform=None, software_version="18.2R1.9")
        self.assertIsNone(device.software_version)
        self.assertFalse(SoftwareVersion.objects.exists())

    def test_a_version_nautobot_refuses_is_reported_and_the_device_still_written(self):
        with patch.object(SoftwareVersion, "validated_save", side_effect=ValidationError("refused")):
            device = self.written(software_version="18.2R1.9")
        self.assertIsNone(device.software_version)
        self.assertIn("Unable to create a Software Version 18.2R1.9", job_log_text(self.adapter.job.logger, "error"))

    def model_of(self, name="dev1", **fields):
        """Return a DiffSync Device bound to this test's adapter, as the Nautobot side would load it."""
        return DeviceModel(adapter=self.adapter, name=name, platform=KNOWN_PLATFORM, vendor=KNOWN_VENDOR, **fields)

    def test_an_update_moves_the_device_to_the_reported_version(self):
        self.written(software_version="18.2R1.9")
        self.assertIsNotNone(self.model_of(software_version="18.2R1.9").update({"software_version": "21.3R1.9"}))
        self.assertEqual(NautobotDevice.objects.get(name="dev1").software_version.version, "21.3R1.9")

    def test_a_platform_change_files_the_same_version_under_the_new_platform(self):
        """A Software Version belongs to one Platform, so the old one would name the wrong Platform."""
        self.written(software_version="18.2R1.9")
        other = Platform.objects.create(name="other-platform", manufacturer=self.manufacturer)
        self.model_of(software_version="18.2R1.9").update({"platform": "other-platform"})
        version = NautobotDevice.objects.get(name="dev1").software_version
        self.assertEqual((version.platform, version.version), (other, "18.2R1.9"))

    def test_a_platform_change_on_a_device_with_no_version_assigns_none(self):
        self.written()
        Platform.objects.create(name="other-platform", manufacturer=self.manufacturer)
        self.model_of().update({"platform": "other-platform"})
        self.assertIsNone(NautobotDevice.objects.get(name="dev1").software_version)

    def test_an_update_nautobot_refuses_is_reported_as_unapplied(self):
        self.written()
        with patch.object(SoftwareVersion, "validated_save", side_effect=ValidationError("refused")):
            self.assertIsNone(self.model_of().update({"software_version": "21.3R1.9"}))

    def test_a_queued_device_carries_its_version_on_the_insert(self):
        """The version is written straight away, so a Device queued in Bulk Write Mode can point at it."""
        self.adapter = NautobotDiffSync(
            job=MagicMock(),
            sync=None,
            sync_ipfabric_tagged_only=False,
            location_filter=None,
            scope=scope_without(),
            bulk_write_mode=True,
        )
        self.create_device(name="queued", software_version="18.2R1.9")
        self.assertFalse(NautobotDevice.objects.filter(name="queued").exists())
        self.adapter.flush_pending_writes()
        self.assertEqual(NautobotDevice.objects.get(name="queued").software_version.version, "18.2R1.9")


class TestWhichVersionNautobotReports(SupportingObjectTestCase):
    """What the Nautobot adapter reports for a Device's software version."""

    def setUp(self):
        super().setUp()
        prepare(self)

    def written(self, name="dev1", **overrides):
        """Create a Device through the sync's own model and return the Nautobot record."""
        return written(self, name, **overrides)

    def loaded(self, scope=None, devices_without_a_software_version=None):
        """Return the Nautobot adapter's model of `dev1` after a load."""
        adapter = NautobotDiffSync(
            job=MagicMock(),
            sync=None,
            sync_ipfabric_tagged_only=False,
            location_filter=None,
            scope=scope if scope is not None else scope_without(),
            devices_without_a_software_version=devices_without_a_software_version,
        )
        adapter.load()
        return adapter.get("device", "dev1")

    def test_the_version_a_device_holds_is_reported(self):
        self.written(software_version="18.2R1.9")
        self.assertEqual(self.loaded().software_version, "18.2R1.9")

    def test_a_device_ip_fabric_reports_no_version_for_reports_none(self):
        """Reported on one side only, the difference would be diffed on every run and never applied."""
        self.written(software_version="18.2R1.9")
        self.assertIsNone(self.loaded(devices_without_a_software_version={"dev1"}).software_version)

    def test_out_of_scope_no_version_is_reported(self):
        self.written(software_version="18.2R1.9")
        self.assertIsNone(self.loaded(scope=scope_without("software_versions")).software_version)
