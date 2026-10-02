"""Unit test for LibreNMS object models."""

from unittest.mock import MagicMock, patch

from django.contrib.contenttypes.models import ContentType
from nautobot.apps.testing import TestCase
from nautobot.dcim.models import Device, Location, LocationType
from nautobot.extras.models import JobResult, Status

from nautobot_ssot.integrations.librenms.diffsync.adapters.librenms import LibrenmsAdapter
from nautobot_ssot.integrations.librenms.jobs import LibrenmsDataSource
from nautobot_ssot.integrations.librenms.utils.nautobot import clear_network_driver_caches
from nautobot_ssot.tests.librenms.fixtures import DEVICE_FIXTURE_RECV, LOCATION_FIXURE_RECV


class TestLibreNMSAdapterTestCase(TestCase):
    """Test NautobotSsotLibreNMSAdapter class."""

    databases = ("default", "job_logs")

    def __init__(self, *args, **kwargs):
        """Initialize test case."""
        super().__init__(*args, **kwargs)

    @classmethod
    def setUpTestData(cls):
        """Setup shared objects for tests."""
        # Create Active status first
        cls.active_status, _ = Status.objects.get_or_create(
            name="Active",
            defaults={
                "color": "4caf50",
            },
        )
        cls.active_status.content_types.add(ContentType.objects.get_for_model(Device))
        cls.active_status.content_types.add(ContentType.objects.get_for_model(Location))

        cls.librenms_client = MagicMock()
        cls.librenms_client.name = "Test"
        cls.librenms_client.remote_url = "https://test.com"
        cls.librenms_client.verify_ssl = True

        # Mock device and location data
        cls.librenms_client.get_librenms_devices.return_value = DEVICE_FIXTURE_RECV
        cls.librenms_client.get_librenms_locations.return_value = LOCATION_FIXURE_RECV

        cls.job = LibrenmsDataSource()
        cls.job.hostname_field = "sysName"
        cls.job.sync_locations = True
        cls.job.location_type = LocationType.objects.get_or_create(name="Site")[0]
        cls.job.default_role = MagicMock()
        cls.job.default_role.name = "network"
        cls.job.tenant = None  # No tenant for test
        cls.job.logger.warning = MagicMock()
        cls.job.sync_locations = True
        cls.job.job_result = JobResult.objects.create(name=cls.job.class_path, task_name="fake task", worker="default")
        cls.librenms_adapter = LibrenmsAdapter(job=cls.job, sync=None, librenms_api=cls.librenms_client)

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


class TestLibreNMSAdapterPlatformResolution(TestCase):
    """Test how the LibreNMS adapter resolves a device OS into a DiffSync platform value."""

    databases = ("default", "job_logs")

    def setUp(self):
        """Build an adapter whose only job is to load one crafted device."""
        super().setUp()
        clear_network_driver_caches()
        self.addCleanup(clear_network_driver_caches)

        self.active_status, _ = Status.objects.get_or_create(name="Active", defaults={"color": "4caf50"})
        self.active_status.content_types.add(ContentType.objects.get_for_model(Device))

        self.job = LibrenmsDataSource()
        self.job.hostname_field = "sysName"
        self.job.sync_locations = False
        self.job.location_type = LocationType.objects.get_or_create(name="Site")[0]
        self.job.default_role = MagicMock()
        self.job.default_role.name = "network"
        self.job.tenant = None
        self.job.debug = False
        self.job.location_map = None
        self.job.hostname_map = None
        self.job.unpermitted_values = None
        self.job.job_result = JobResult.objects.create(
            name=self.job.class_path, task_name="fake task", worker="default"
        )

        self.librenms_client = MagicMock()
        self.adapter = LibrenmsAdapter(job=self.job, sync=None, librenms_api=self.librenms_client)
        self.adapter.lnms_api.get_librenms_ipinfo_for_device_ip.return_value = None

    def _device(self, librenms_os):
        """Return a minimal LibreNMS device payload with the given OS."""
        device = dict(DEVICE_FIXTURE_RECV["devices"][0])
        device["os"] = librenms_os
        device["ip"] = None
        return device

    def _load_platform(self, librenms_os, consolidated):
        """Load one device and return the platform value it produced."""
        self.adapter.consolidated_platforms = consolidated
        valid = {
            "sysName": {"valid": True},
            "location": {"valid": True},
            "role": {"valid": True},
            "platform": {"valid": True},
            "device_type": {"valid": True},
        }
        with (
            patch(
                "nautobot_ssot.integrations.librenms.diffsync.adapters.librenms.has_required_values",
                return_value=valid,
            ),
            patch.dict(
                "nautobot_ssot.integrations.librenms.constants.PLUGIN_CFG",
                {"librenms_permitted_values": {"role": ["network"]}},
            ),
        ):
            self.adapter.load_device(device=self._device(librenms_os))
        loaded = list(self.adapter.get_all("device"))
        self.assertEqual(len(loaded), 1, f"Expected exactly one loaded device, got {loaded}")
        return loaded[0].platform

    def test_consolidated_mode_emits_network_driver(self):
        """The routeros fixture device resolves to its netmiko driver."""
        self.assertEqual(self._load_platform("routeros", consolidated=True), "mikrotik_routeros")

    def test_consolidated_mode_falls_back_to_raw_os(self):
        """An unmapped OS (opnsense is ambiguous) keeps its raw value, not an invented driver."""
        self.assertEqual(self._load_platform("opnsense", consolidated=True), "opnsense")

    def test_legacy_mode_emits_fqcn(self):
        """Legacy naming is unchanged."""
        self.assertEqual(self._load_platform("ios", consolidated=False), "cisco.ios.ios")

    def test_legacy_mode_raw_os_unchanged(self):
        """An unmapped OS passes through as the platform name, exactly as before."""
        self.assertEqual(self._load_platform("fortios", consolidated=False), "fortios")

    def test_mode_is_read_from_plugin_config(self):
        """The adapter reads the setting once at construction."""
        with patch.dict(
            "nautobot_ssot.integrations.librenms.constants.PLUGIN_CFG",
            {"librenms_consolidated_platforms": True},
        ):
            adapter = LibrenmsAdapter(job=self.job, sync=None, librenms_api=self.librenms_client)
        self.assertTrue(adapter.consolidated_platforms)

    def test_mode_defaults_to_legacy(self):
        """Absent the setting, the adapter stays in legacy mode."""
        self.assertFalse(self.adapter.consolidated_platforms)
