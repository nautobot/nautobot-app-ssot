"""Unit test for LibreNMS object models."""

from unittest.mock import MagicMock

from django.contrib.contenttypes.models import ContentType
from nautobot.core.testing import TransactionTestCase
from nautobot.dcim.models import Device, Location, LocationType
from nautobot.extras.models import JobResult, Status

from nautobot_ssot.integrations.librenms.diffsync.adapters.librenms import LibrenmsAdapter
from nautobot_ssot.integrations.librenms.jobs import LibrenmsDataSource
from nautobot_ssot.tests.librenms.fixtures import DEVICE_FIXTURE_RECV, LOCATION_FIXURE_RECV


class TestLibreNMSAdapterTestCase(TransactionTestCase):
    """Test NautobotSsotLibreNMSAdapter class."""

    databases = ("default", "job_logs")

    def __init__(self, *args, **kwargs):
        """Initialize test case."""
        super().__init__(*args, **kwargs)

    def setUp(self):
        """Setup shared objects for tests."""
        # Create Active status first
        self.active_status, _ = Status.objects.get_or_create(
            name="Active",
            defaults={
                "color": "4caf50",
            },
        )
        self.active_status.content_types.add(ContentType.objects.get_for_model(Device))
        self.active_status.content_types.add(ContentType.objects.get_for_model(Location))

        self.librenms_client = MagicMock()
        self.librenms_client.name = "Test"
        self.librenms_client.remote_url = "https://test.com"
        self.librenms_client.verify_ssl = True

        # Mock device and location data
        self.librenms_client.get_librenms_devices_from_file.return_value = {
            "count": len(DEVICE_FIXTURE_RECV),
            "devices": DEVICE_FIXTURE_RECV,
        }
        self.librenms_client.get_librenms_locations_from_file.return_value = {
            "count": len(LOCATION_FIXURE_RECV),
            "locations": LOCATION_FIXURE_RECV,
        }

        self.job = LibrenmsDataSource()
        self.job.load_type = "file"
        self.job.hostname_field = "sysName"
        self.job.sync_locations = True
        self.job.location_type = LocationType.objects.get_or_create(name="Site")[0]
        self.job.logger.warning = MagicMock()
        self.job.sync_locations = True
        self.job.job_result = JobResult.objects.create(
            name=self.job.class_path, task_name="fake task", worker="default"
        )
        self.librenms_adapter = LibrenmsAdapter(job=self.job, sync=None, librenms_api=self.librenms_client)

    def test_data_loading(self):
        """Test that devices and locations are loaded correctly."""
        self.librenms_adapter.load()

        # Debugging outputs
        print("Adapter Devices:", list(self.librenms_adapter.get_all("device")))
        print("Adapter Locations:", list(self.librenms_adapter.get_all("location")))

        expected_locations = {loc["location"].strip() for loc in LOCATION_FIXURE_RECV}
        loaded_locations = {loc.get_unique_id() for loc in self.librenms_adapter.get_all("location")}
        self.assertEqual(expected_locations, loaded_locations, "Locations are not loaded correctly.")

        expected_devices = {dev["sysName"].strip() for dev in DEVICE_FIXTURE_RECV}
        loaded_devices = {dev.get_unique_id() for dev in self.librenms_adapter.get_all("device")}
        self.assertEqual(expected_devices, loaded_devices, "Devices are not loaded correctly.")
