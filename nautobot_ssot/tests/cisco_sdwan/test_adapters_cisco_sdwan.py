"""Tests for the Cisco SD-WAN source adapter."""

from unittest.mock import MagicMock, patch

from django.test import TestCase

from nautobot_ssot.integrations.cisco_sdwan.diffsync.adapters.cisco_sdwan import CiscoSdwanRemoteAdapter
from nautobot_ssot.tests.cisco_sdwan.fixtures import attach_interfaces, get_merged_devices


def build_mock_job():
    """Build a mocked Job with the parameters the adapter expects."""
    job = MagicMock()
    job.debug = False
    job.devices = None
    job.model_normalization = "^vedge-"
    job.device_status.name = "Active"
    job.device_role.name = "Router"
    job.device_platform.name = "cisco_ios"
    job.device_platform.manufacturer.name = "Cisco"
    job.device_location.name = "Staging"
    job.device_secrets_group.name = "SDWAN Devices"
    job.device_tenant = None
    return job


def build_adapter(job):
    """Build a CiscoSdwanRemoteAdapter with a mocked SD-WAN Manager client."""
    sdwan_manager = MagicMock()
    sdwan_manager.get_devices.return_value = get_merged_devices()
    sdwan_manager.get_interfaces.side_effect = attach_interfaces
    with patch(
        "nautobot_ssot.integrations.cisco_sdwan.diffsync.adapters.cisco_sdwan.CiscoSdwanManager",
        return_value=sdwan_manager,
    ):
        return CiscoSdwanRemoteAdapter(job=job, sync=None)


class TestCiscoSdwanRemoteAdapter(TestCase):
    """Test the CiscoSdwanRemoteAdapter class."""

    def setUp(self):
        """Initialize the adapter with a mocked SD-WAN Manager client."""
        self.job = build_mock_job()
        self.adapter = build_adapter(self.job)
        self.adapter.load()

    def test_load_devices(self):
        """Validate Devices are loaded, keyed by hostname."""
        self.assertEqual(
            {"sdwan-edge-01", "sdwan-edge-02", "vmanage-01"},
            {device.get_unique_id() for device in self.adapter.get_all("device")},
        )

    def test_device_attributes(self):
        """Validate Device attributes including model normalization and serial extraction."""
        device = self.adapter.get("device", "sdwan-edge-01")
        self.assertEqual(device.device_type__model, "C8000V")
        self.assertEqual(device.serial, "AAAA1111BBBB")
        self.assertEqual(device.status__name, "Active")
        self.assertEqual(device.role__name, "Router")
        self.assertEqual(device.location__name, "Staging")
        self.assertEqual(device.secrets_group__name, "SDWAN Devices")
        self.assertIsNone(device.tenant__name)
        self.assertEqual(device.software_version__version, "17.06.03a")
        self.assertEqual(device.software_version__platform__name, "cisco_ios")

    def test_load_device_types(self):
        """Validate normalized DeviceTypes are loaded once per model."""
        self.assertEqual(
            {"C8000V__Cisco", "ISR4451-X__Cisco", "vmanage__Cisco"},
            {device_type.get_unique_id() for device_type in self.adapter.get_all("device_type")},
        )

    def test_load_software_versions(self):
        """Validate normalized SoftwareVersions are loaded once per version."""
        self.assertEqual(
            {"cisco_ios__17.06.03a__Active", "cisco_ios__17.09.04__Active", "cisco_ios__20.06.03__Active"},
            {version.get_unique_id() for version in self.adapter.get_all("software_version")},
        )

    def test_load_interfaces(self):
        """Validate Interfaces are loaded and exclusions honored."""
        interface_ids = {interface.get_unique_id() for interface in self.adapter.get_all("interface")}
        self.assertEqual(
            {
                "sdwan-edge-01__GigabitEthernet1",
                "sdwan-edge-01__GigabitEthernet2",
                "sdwan-edge-01__Tunnel1",
                "sdwan-edge-01__system",
                "sdwan-edge-02__GigabitEthernet0/0/0",
                "sdwan-edge-02__GigabitEthernet0/0/1",
            },
            interface_ids,
        )
        # Loopback65528 is excluded by default
        self.assertNotIn("sdwan-edge-01__Loopback65528", interface_ids)

    def test_interface_attributes(self):
        """Validate Interface attribute normalization."""
        interface = self.adapter.get("interface", {"device__name": "sdwan-edge-01", "name": "GigabitEthernet1"})
        self.assertEqual(interface.mtu, 1500)
        self.assertEqual(interface.description, "WAN uplink")
        self.assertTrue(interface.enabled)
        # MTU of "0" is treated as undefined and "down" is not an up state
        interface = self.adapter.get("interface", {"device__name": "sdwan-edge-01", "name": "GigabitEthernet2"})
        self.assertIsNone(interface.mtu)
        self.assertFalse(interface.enabled)

    def test_load_ip_addresses(self):
        """Validate IP assignments are loaded and null/excluded addresses skipped."""
        assignment_ids = {assignment.get_unique_id() for assignment in self.adapter.get_all("ip_address_to_interface")}
        self.assertEqual(
            {
                "sdwan-edge-01__GigabitEthernet1__192.0.2.10__24",
                "sdwan-edge-01__GigabitEthernet2__198.51.100.5__30",
                "sdwan-edge-01__system__10.255.1.1__32",
                "sdwan-edge-02__GigabitEthernet0/0/1__203.0.113.9__29",
            },
            assignment_ids,
        )
        # 169.254.10.1 on Tunnel1 is within an excluded prefix, "-" on Gi0/0/0 is a null address
        self.assertNotIn("sdwan-edge-01__Tunnel1__169.254.10.1__24", assignment_ids)

    def test_ip_address_vrf(self):
        """Validate the VPN ID is mapped to the Interface VRF."""
        assignment = self.adapter.get(
            "ip_address_to_interface",
            {
                "interface__device__name": "sdwan-edge-01",
                "interface__name": "GigabitEthernet2",
                "ip_address__host": "198.51.100.5",
                "ip_address__mask_length": 30,
            },
        )
        self.assertEqual(assignment.interface__vrf__name, "10")


class TestCiscoSdwanRemoteAdapterEdgeCases(TestCase):
    """Test the CiscoSdwanRemoteAdapter debug logging and invalid data handling."""

    def setUp(self):
        """Initialize the adapter without loading it."""
        self.job = build_mock_job()
        self.adapter = build_adapter(self.job)

    def test_load_with_debug_logging(self):
        """Validate the load emits debug logs for every object when debug is enabled."""
        self.job.debug = True
        self.adapter.load()
        self.assertTrue(self.job.logger.debug.called)
        debug_messages = " ".join(str(call) for call in self.job.logger.debug.call_args_list)
        self.assertIn("Device Type:", debug_messages)
        self.assertIn("Software Version:", debug_messages)
        self.assertIn("Interface:", debug_messages)
        self.assertIn("Excluded IP", debug_messages)

    def test_validate_ip_address_invalid_mask(self):
        """Validate an invalid subnet mask is skipped with an error."""
        interface = {
            "ip-address": "192.0.2.10",
            "ipv4-subnet-mask": "not-a-mask",
            "ifname": "GigabitEthernet1",
            "vdevice-name": "10.255.1.1",
        }
        result = self.adapter._validate_ip_address(interface)  # pylint: disable=protected-access
        self.assertIsNone(result)
        self.job.logger.error.assert_called_once()

    def test_validate_ip_address_invalid_ip(self):
        """Validate an invalid IP address is skipped with an error."""
        interface = {
            "ip-address": "999.999.999.999",
            "ipv4-subnet-mask": "",
            "ifname": "GigabitEthernet1",
            "vdevice-name": "10.255.1.1",
        }
        result = self.adapter._validate_ip_address(interface)  # pylint: disable=protected-access
        self.assertIsNone(result)
        self.job.logger.error.assert_called_once()
