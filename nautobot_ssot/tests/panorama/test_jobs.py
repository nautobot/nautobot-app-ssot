"""Tests for PanoramaDataSource job."""

import uuid
from unittest.mock import MagicMock, patch

from diffsync import DiffSyncFlags
from nautobot.core.testing import TransactionTestCase
from nautobot.dcim.models import Controller, Device, DeviceType, Location, LocationType, Manufacturer, Platform
from nautobot.extras.models import JobResult, MetadataType, ObjectMetadata, Role, Status

from nautobot_ssot.integrations.panorama.jobs import PanoramaDataSource


class TestPanoramaDataSource(TransactionTestCase):  # pylint: disable=too-many-instance-attributes
    """Test PanoramaDataSource job class."""

    job_class = PanoramaDataSource
    databases = ("default", "job_logs")

    def setUp(self):
        # pylint: disable=duplicate-code, R0801
        """Per-test setup."""
        super().setUp()
        self.status_active, _ = Status.objects.get_or_create(name="Active")
        self.device_role, _ = Role.objects.get_or_create(name="Firewall")
        self.manufacturer, _ = Manufacturer.objects.get_or_create(name="Palo Alto")
        self.platform, _ = Platform.objects.get_or_create(name="paloalto_panos")
        self.device_type, _ = DeviceType.objects.get_or_create(
            model="PA-3220",
            part_number="PAN-PA-3220",
            manufacturer=self.manufacturer,
        )
        self.location_type, _ = LocationType.objects.get_or_create(name="Site")
        self.location, _ = Location.objects.get_or_create(
            name="Test Site",
            location_type=self.location_type,
            status=self.status_active,
        )
        self.device, _ = Device.objects.get_or_create(
            name="fw-01",
            serial="serial001",
            device_type=self.device_type,
            platform=self.platform,
            role=self.device_role,
            status=self.status_active,
            location=self.location,
        )
        self.controller, _ = Controller.objects.get_or_create(
            name="panorama-01",
            location=self.location,
            status=self.status_active,
        )
        self.job_result = JobResult.objects.create(
            name=self.job_class.class_path,
            task_name="Test",
            user=None,
            id=uuid.uuid4(),
        )
        self.metadata_type, _ = MetadataType.objects.get_or_create(
            name="Last Panorama Sync",
            defaults={"description": "Last sync from Panorama"},
        )

    def test_job_instantiation(self):
        """Test job can be instantiated."""
        job = PanoramaDataSource()
        self.assertIsInstance(job, PanoramaDataSource)

    def test_data_mappings_returns_tuple(self):
        """Test data_mappings returns a tuple."""
        mappings = PanoramaDataSource.data_mappings()
        self.assertIsInstance(mappings, tuple)

    def test_data_mappings_count(self):
        """Test data_mappings returns expected number of mappings."""
        mappings = PanoramaDataSource.data_mappings()
        self.assertEqual(len(mappings), 4)

    def test_config_information(self):
        """Test config_information returns a dict."""
        config = PanoramaDataSource.config_information()
        self.assertIsInstance(config, dict)

    def test_default_attributes(self):
        """Test default attribute values."""
        job = PanoramaDataSource()
        self.assertEqual(job.diffsync_flags, DiffSyncFlags.CONTINUE_ON_FAILURE)
        self.assertEqual(job.loaded_panorama_devices, set())
        self.assertIsNone(job.filtered_device_serials)

    def test_run_sets_instance_attributes(self):
        """Test run method sets instance attributes."""
        job = PanoramaDataSource()
        job.logger = MagicMock()
        job.job_result = self.job_result
        job.sync = MagicMock()

        with patch("nautobot_ssot.integrations.panorama.jobs.DataSource.run", return_value=None):
            job.run(
                dryrun=False,
                debug=True,
                default_device_status=self.status_active,
                panorama_controller=self.controller,
                devices=[],
            )

        self.assertTrue(job.debug)
        self.assertFalse(job.dryrun)
        self.assertEqual(job.default_device_status, self.status_active)
        self.assertEqual(job.panorama_controller, self.controller)
        self.assertEqual(job.devices, [])

    def test_run_with_devices_filters(self):
        """Test run method filters devices correctly."""
        job = PanoramaDataSource()
        job.logger = MagicMock()
        job.job_result = self.job_result
        job.sync = MagicMock()

        with patch("nautobot_ssot.integrations.panorama.jobs.DataSource.run", return_value=None):
            job.run(
                dryrun=False,
                debug=False,
                default_device_status=self.status_active,
                panorama_controller=self.controller,
                devices=[self.device],
            )

        self.assertEqual(job.filtered_device_serials, ["serial001"])

    def test_run_empty_filter_logs_error(self):
        """Test run method logs error when filtered devices is empty."""
        job = PanoramaDataSource()
        job.logger = MagicMock()
        job.job_result = self.job_result
        job.sync = MagicMock()

        with patch("nautobot_ssot.integrations.panorama.jobs.Device.objects") as mock_objects:
            mock_query = MagicMock()
            mock_query.count.return_value = 0
            mock_query.__bool__ = MagicMock(return_value=False)
            mock_objects.filter.return_value = mock_query

            with patch("nautobot_ssot.integrations.panorama.jobs.DataSource.run", return_value=None):
                job.run(
                    dryrun=False,
                    debug=False,
                    default_device_status=self.status_active,
                    panorama_controller=self.controller,
                    devices=[self.device],
                )

                job.logger.error.assert_called_with(
                    "No devices match the job form filter, no devices will be processed."
                )

    def test_run_calls_parent(self):
        """Test run method calls parent run method."""
        job = PanoramaDataSource()
        job.logger = MagicMock()
        job.job_result = self.job_result

        with patch("nautobot_ssot.integrations.panorama.jobs.DataSource.run") as mock_parent_run:
            mock_parent_run.return_value = None

            job.run(
                dryrun=False,
                debug=False,
                default_device_status=self.status_active,
                panorama_controller=self.controller,
                devices=[],
            )

            mock_parent_run.assert_called_once()

    def test_load_source_adapter(self):
        """Test load_source_adapter creates panorama adapter."""
        job = PanoramaDataSource()
        job.logger = MagicMock()
        job.job_result = self.job_result
        job.panorama_controller = self.controller
        job.sync = MagicMock()

        with patch("nautobot_ssot.integrations.panorama.jobs.panorama.PanoSSoTPanoramaAdapter") as mock_adapter:
            mock_instance = MagicMock()
            mock_adapter.return_value = mock_instance

            job.load_source_adapter()

            mock_adapter.assert_called_once_with(job=job, sync=job.sync, pan=self.controller)
            mock_instance.load.assert_called_once()

    def test_load_target_adapter(self):
        """Test load_target_adapter creates nautobot adapter."""
        job = PanoramaDataSource()
        job.logger = MagicMock()
        job.job_result = self.job_result
        job.sync = MagicMock()

        with patch("nautobot_ssot.integrations.panorama.jobs.nautobot.PanoSSoTNautobotAdapter") as mock_adapter:
            mock_instance = MagicMock()
            mock_adapter.return_value = mock_instance

            job.load_target_adapter()

            mock_adapter.assert_called_once_with(job=job, sync=job.sync)
            mock_instance.load.assert_called_once()

    def test_on_success_creates_metadata(self):
        """Test on_success creates ObjectMetadata when none exists."""
        job = PanoramaDataSource()
        job.logger = MagicMock()
        job.job_result = self.job_result
        job.dryrun = False
        job.loaded_panorama_devices = {"serial001"}

        job.on_success(None, "task_id", {}, {})

        metadata = ObjectMetadata.objects.filter(metadata_type=self.metadata_type, assigned_object_id=self.device.id)
        self.assertEqual(metadata.count(), 1)

    def test_on_success_updates_existing_metadata(self):
        """Test on_success updates existing ObjectMetadata."""
        existing_metadata = ObjectMetadata.objects.create(
            metadata_type=self.metadata_type,
            assigned_object=self.device,
            scoped_fields=["name"],
            value="2020-01-01T00:00:00Z",
        )

        job = PanoramaDataSource()
        job.logger = MagicMock()
        job.job_result = self.job_result
        job.dryrun = False
        job.loaded_panorama_devices = {"serial001"}

        job.on_success(None, "task_id", {}, {})

        existing_metadata.refresh_from_db()
        self.assertNotEqual(existing_metadata.value, "2020-01-01T00:00:00Z")

    def test_on_success_skips_missing_device(self):
        """Test on_success handles missing device gracefully."""
        job = PanoramaDataSource()
        job.logger = MagicMock()
        job.job_result = self.job_result
        job.dryrun = False
        job.loaded_panorama_devices = {"nonexistent_serial"}

        job.on_success(None, "task_id", {}, {})

        job.logger.error.assert_not_called()

    def test_on_success_does_nothing_on_dryrun(self):
        """Test on_success does nothing when dryrun is True."""
        job = PanoramaDataSource()
        job.logger = MagicMock()
        job.job_result = self.job_result
        job.dryrun = True
        job.loaded_panorama_devices = {"serial001"}

        job.on_success(None, "task_id", {}, {})

        metadata = ObjectMetadata.objects.filter(metadata_type=self.metadata_type, assigned_object_id=self.device.id)
        self.assertEqual(metadata.count(), 0)
