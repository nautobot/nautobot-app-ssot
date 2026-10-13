"""Tests for recording the image file IP Fabric reports for each Device as a Nautobot Software Image File."""

from collections import defaultdict
from unittest.mock import MagicMock, patch

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase
from ipfabric.models.device import Device as IPFabricDevice
from nautobot.dcim.models import Device as NautobotDevice
from nautobot.dcim.models import SoftwareImageFile, SoftwareVersion

from nautobot_ssot.integrations.ipfabric.bulk_writes import THROUGH_LEVELS
from nautobot_ssot.integrations.ipfabric.diffsync.adapter_nautobot import NautobotDiffSync
from nautobot_ssot.integrations.ipfabric.diffsync.diffsync_models import Device as DeviceModel
from nautobot_ssot.integrations.ipfabric.sync_scope import SyncScope
from nautobot_ssot.integrations.ipfabric.utilities import nbutils
from nautobot_ssot.integrations.ipfabric.utilities.utils import software_image_name
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
from nautobot_ssot.tests.ipfabric.test_software_versions import prepare, written

IMAGE = "c3750e-universalk9-mz.150-2.se10a.bin"


class TestTheImageFileName(SimpleTestCase):
    """Reducing what IP Fabric reports to the image's file name."""

    def test_the_location_is_dropped_and_the_name_lowercased(self):
        for reported, expected in (
            ("flash:/c3750e-universalk9-mz.150-2.SE10a.bin", IMAGE),
            ("flash:c3750e-universalk9-mz.150-2.SE10a.bin", IMAGE),
            ("boot:/asa9203-10-smp-k8.bin", "asa9203-10-smp-k8.bin"),
            ("flash0:/vios-adventerprisek9-m", "vios-adventerprisek9-m"),
            ("bootflash:/sub/dir/image.bin", "image.bin"),
            ("image.bin", "image.bin"),
        ):
            with self.subTest(reported=reported):
                self.assertEqual(expected, software_image_name(reported))

    def test_nothing_reported_is_no_image(self):
        for reported in (None, "", "flash:/"):
            with self.subTest(reported=reported):
                self.assertIsNone(software_image_name(reported))


class TestWhichImageIsLoaded(SupportingObjectTestCase):
    """What the IP Fabric adapter reports for a Device's image."""

    def loaded(self, sync_software_images=True, **overrides):
        """Return `(devices keyed by name, the adapter)` over the fixtures, with overrides applied."""
        client = mock_ipfabric_client()
        client.devices.by_site = defaultdict(list)
        for record in DEVICE_INVENTORY_FIXTURE:
            record = dict(record, **overrides)
            client.devices.by_site[record["siteName"]].append(IPFabricDevice(**record))  # pylint: disable=no-member
        adapter = build_adapter(client=client, sync_software_versions=True, sync_software_images=sync_software_images)
        return {device.name: device for device in adapter.get_all("device")}, adapter

    def test_the_reported_image_is_loaded_by_its_file_name(self):
        devices, adapter = self.loaded(image="flash:/c3750e-universalk9-mz.150-2.SE10a.bin")
        self.assertEqual(IMAGE, devices["nyc-rtr-01"].software_image)
        self.assertEqual(adapter.devices_without_a_software_image, set())

    def test_a_device_reporting_no_image_is_registered_as_absent(self):
        devices, adapter = self.loaded(image=None)
        self.assertIsNone(devices["nyc-rtr-01"].software_image)
        self.assertIn("nyc-rtr-01", adapter.devices_without_a_software_image)

    def test_a_device_with_no_version_has_no_image_to_report(self):
        """An image belongs to a Software Version, so without one it has nowhere to go."""
        devices, adapter = self.loaded(image="flash:/image.bin", version=None)
        self.assertIsNone(devices["nyc-rtr-01"].software_image)
        self.assertIn("nyc-rtr-01", adapter.devices_without_a_software_image)

    def test_out_of_scope_nothing_is_reported_or_registered(self):
        devices, adapter = self.loaded(sync_software_images=False, image="flash:/image.bin")
        self.assertIsNone(devices["nyc-rtr-01"].software_image)
        self.assertEqual(adapter.devices_without_a_software_image, set())

    def test_images_need_versions_in_scope(self):
        self.assertFalse(SyncScope(["software_images"]).software_images)
        self.assertTrue(SyncScope(["software_versions", "software_images"]).software_images)

    def test_off_unless_selected(self):
        self.assertFalse(SyncScope.from_job_kwargs({}).software_images)


class TestWritingTheImage(SupportingObjectTestCase):
    """What reaches Nautobot when the sync creates or updates a Device with an image."""

    def setUp(self):
        super().setUp()
        prepare(self)

    def written(self, name="dev1", **overrides):
        """Create a Device through the sync's own model and return the Nautobot record."""
        return written(self, name, **overrides)

    def model_of(self, name="dev1", **fields):
        """Return a DiffSync Device bound to this test's adapter, as the Nautobot side would load it."""
        return DeviceModel(adapter=self.adapter, name=name, platform=KNOWN_PLATFORM, vendor=KNOWN_VENDOR, **fields)

    def test_a_new_device_runs_its_image_under_its_version(self):
        device = self.written(software_version="15.0", software_image=IMAGE)
        image = device.software_image_files.get()
        self.assertEqual((image.image_file_name, image.software_version.version), (IMAGE, "15.0"))
        self.assertEqual(image.status.name, "Active")
        self.assertTrue(image.tags.filter(name="SSoT Synced from IPFabric").exists())

    def test_the_image_is_mapped_to_the_device_type_running_it(self):
        """Nautobot refuses an image on a Device unless the image is mapped to the Device's type."""
        image = self.written(software_version="15.0", software_image=IMAGE).software_image_files.get()
        self.assertEqual(list(image.device_types.all()), [self.device_type])

    def test_an_image_nautobot_holds_is_used_rather_than_duplicated(self):
        version = SoftwareVersion.objects.create(platform=self.platform, version="15.0", status=self.active_status)
        existing = SoftwareImageFile.objects.create(
            software_version=version, image_file_name=IMAGE, status=self.active_status
        )
        self.written("dev1", software_version="15.0", software_image=IMAGE)
        self.written("dev2", software_version="15.0", software_image=IMAGE)
        self.assertEqual(SoftwareImageFile.objects.count(), 1)
        self.assertEqual(list(NautobotDevice.objects.get(name="dev2").software_image_files.all()), [existing])

    def test_an_image_held_in_another_case_is_reused(self):
        version = SoftwareVersion.objects.create(platform=self.platform, version="15.0", status=self.active_status)
        existing = SoftwareImageFile.objects.create(
            software_version=version, image_file_name=IMAGE.upper(), status=self.active_status
        )
        device = self.written(software_version="15.0", software_image=IMAGE)
        self.assertEqual(SoftwareImageFile.objects.count(), 1)
        self.assertEqual(list(device.software_image_files.all()), [existing])

    def test_the_image_lookup_is_cached_for_the_run(self):
        self.assertTrue(hasattr(nbutils.get_or_create_software_image, "cache_info"))

    def test_a_device_with_no_version_is_written_without_an_image(self):
        device = self.written(platform=None, software_version="15.0", software_image=IMAGE)
        self.assertFalse(device.software_image_files.exists())

    def test_an_image_nautobot_refuses_is_reported_and_the_device_still_written(self):
        with patch.object(SoftwareImageFile, "validated_save", side_effect=ValidationError("refused")):
            device = self.written(software_version="15.0", software_image=IMAGE)
        self.assertFalse(device.software_image_files.exists())
        self.assertIn(
            f"Unable to record the Software Image File {IMAGE}", job_log_text(self.adapter.job.logger, "error")
        )

    def test_an_update_replaces_the_image_the_device_runs(self):
        self.written(software_version="15.0", software_image=IMAGE)
        model = self.model_of(software_version="15.0", software_image=IMAGE)
        self.assertIsNotNone(model.update({"software_image": "other.bin"}))
        names = NautobotDevice.objects.get(name="dev1").software_image_files.values_list("image_file_name", flat=True)
        self.assertEqual(list(names), ["other.bin"])

    def test_a_version_change_files_the_image_under_the_new_version(self):
        self.written(software_version="15.0", software_image=IMAGE)
        self.model_of(software_version="15.0", software_image=IMAGE).update({"software_version": "15.1"})
        image = NautobotDevice.objects.get(name="dev1").software_image_files.get()
        self.assertEqual((image.image_file_name, image.software_version.version), (IMAGE, "15.1"))

    def test_a_version_change_with_no_image_reported_drops_the_old_versions_image(self):
        self.written(software_version="15.0", software_image=IMAGE)
        self.model_of(software_version="15.0").update({"software_version": "15.1"})
        self.assertFalse(NautobotDevice.objects.get(name="dev1").software_image_files.exists())

    def test_an_image_of_the_new_version_is_kept(self):
        device = self.written(software_version="15.0", software_image=IMAGE)
        new_version = SoftwareVersion.objects.create(platform=self.platform, version="15.1", status=self.active_status)
        current = SoftwareImageFile.objects.create(
            software_version=new_version, image_file_name="current.bin", status=self.active_status
        )
        current.device_types.add(self.device_type)
        device.software_image_files.add(current)
        self.model_of(software_version="15.0").update({"software_version": "15.1"})
        self.assertEqual(list(NautobotDevice.objects.get(name="dev1").software_image_files.all()), [current])

    def test_out_of_scope_images_are_left_alone_when_the_version_changes(self):
        self.written(software_version="15.0", software_image=IMAGE)
        self.adapter.scope = scope_without("software_images")
        self.model_of(software_version="15.0").update({"software_version": "15.1"})
        self.assertTrue(NautobotDevice.objects.get(name="dev1").software_image_files.exists())

    def test_an_update_nautobot_refuses_is_reported_as_unapplied(self):
        self.written(software_version="15.0")
        with patch.object(SoftwareImageFile, "validated_save", side_effect=ValidationError("refused")):
            self.assertIsNone(self.model_of(software_version="15.0").update({"software_image": IMAGE}))

    def test_a_queued_device_gets_its_image_once_written(self):
        """The Device has no row while queued, so the join row is queued after it."""
        self.assertIn(NautobotDevice.software_image_files.through, THROUGH_LEVELS)
        self.adapter = NautobotDiffSync(
            job=MagicMock(),
            sync=None,
            sync_ipfabric_tagged_only=False,
            location_filter=None,
            scope=scope_without(),
            bulk_write_mode=True,
        )
        self.create_device(name="queued", software_version="15.0", software_image=IMAGE)
        self.adapter.flush_pending_writes()
        names = NautobotDevice.objects.get(name="queued").software_image_files.values_list("image_file_name", flat=True)
        self.assertEqual(list(names), [IMAGE])


class TestWhichImageNautobotReports(SupportingObjectTestCase):
    """What the Nautobot adapter reports for a Device's image."""

    def setUp(self):
        super().setUp()
        prepare(self)

    def loaded(self, scope=None, devices_without_a_software_image=None):
        """Return the Nautobot adapter's model of `dev1` after a load."""
        adapter = NautobotDiffSync(
            job=MagicMock(),
            sync=None,
            sync_ipfabric_tagged_only=False,
            location_filter=None,
            scope=scope if scope is not None else scope_without(),
            devices_without_a_software_image=devices_without_a_software_image,
        )
        adapter.load()
        return adapter.get("device", "dev1")

    def test_the_image_a_device_runs_is_reported(self):
        written(self, software_version="15.0", software_image=IMAGE)
        self.assertEqual(self.loaded().software_image, IMAGE)

    def test_several_images_are_reported_together_so_they_are_replaced_by_the_one_reported(self):
        device = written(self, software_version="15.0", software_image=IMAGE)
        extra = SoftwareImageFile.objects.create(
            software_version=device.software_version, image_file_name="a-extra.bin", status=self.active_status
        )
        extra.device_types.add(self.device_type)
        device.software_image_files.add(extra)
        self.assertEqual(self.loaded().software_image, f"a-extra.bin, {IMAGE}")

    def test_a_device_running_no_image_reports_none(self):
        written(self, software_version="15.0")
        self.assertIsNone(self.loaded().software_image)

    def test_a_device_ip_fabric_reports_no_image_for_reports_none(self):
        written(self, software_version="15.0", software_image=IMAGE)
        self.assertIsNone(self.loaded(devices_without_a_software_image={"dev1"}).software_image)

    def test_an_image_held_in_another_case_is_reported_as_ip_fabric_names_it(self):
        """The IP Fabric side reports the name lowercased, so this side must too or it never converges."""
        device = written(self, software_version="15.0", software_image=IMAGE)
        device.software_image_files.update(image_file_name=IMAGE.upper())
        self.assertEqual(self.loaded().software_image, IMAGE)

    def test_out_of_scope_no_image_is_reported(self):
        written(self, software_version="15.0", software_image=IMAGE)
        self.assertIsNone(self.loaded(scope=scope_without("software_images")).software_image)
