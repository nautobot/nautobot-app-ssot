"""Unit test for LibreNMS object models."""

from unittest.mock import MagicMock, patch

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
        self.librenms_client.get_librenms_devices.return_value = DEVICE_FIXTURE_RECV
        self.librenms_client.get_librenms_locations.return_value = LOCATION_FIXURE_RECV

        self.job = LibrenmsDataSource()
        self.job.hostname_field = "sysName"
        self.job.sync_locations = True
        self.job.location_type = LocationType.objects.get_or_create(name="Site")[0]
        self.job.default_role = MagicMock()
        self.job.default_role.name = "network"
        self.job.tenant = None  # No tenant for test
        self.job.logger.warning = MagicMock()
        self.job.sync_locations = True
        self.job.job_result = JobResult.objects.create(
            name=self.job.class_path, task_name="fake task", worker="default"
        )
        self.librenms_adapter = LibrenmsAdapter(job=self.job, sync=None, librenms_api=self.librenms_client)

    @patch("nautobot_ssot.integrations.librenms.diffsync.adapters.librenms.has_required_values")
    def test_data_loading(self, mock_has_required_values):
        """Test that devices and locations are loaded correctly."""

        def mock_validation(device_dict, job):
            """Mock validation to return valid for GRCH-AP-P2-UTPO-303-60, invalid for others."""
            # Check if this is the device we want to test
            hostname_field = getattr(job, "hostname_field", "hostname")
            device_name = device_dict.get(hostname_field, "")

            if device_name == "GRCH-AP-P2-UTPO-303-60":
                # Return valid for our test device
                return {
                    hostname_field: {"valid": True},
                    "location": {"valid": True},
                    "role": {"valid": True},
                    "platform": {"valid": True},
                    "device_type": {"valid": True},
                }
            # Return invalid for all other devices - just need one field to be invalid
            return {
                hostname_field: {"valid": False, "reason": "Test validation failure"},
            }

        mock_has_required_values.side_effect = mock_validation

        self.librenms_adapter.load()

        # Debugging outputs
        print("Adapter Devices:", list(self.librenms_adapter.get_all("device")))
        print("Adapter Locations:", list(self.librenms_adapter.get_all("location")))

        # Check that the specific device was loaded
        loaded_devices = list(self.librenms_adapter.get_all("device"))
        device_names = [dev.name for dev in loaded_devices]

        self.assertIn(
            "GRCH-AP-P2-UTPO-303-60",
            device_names,
            f"Expected device GRCH-AP-P2-UTPO-303-60 not found in loaded devices: {device_names}",
        )

        # Check that locations were loaded
        loaded_locations = list(self.librenms_adapter.get_all("location"))
        self.assertGreater(len(loaded_locations), 0, "No locations were loaded")
