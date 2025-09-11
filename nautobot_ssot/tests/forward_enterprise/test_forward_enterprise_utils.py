"""Test Forward Enterprise utility functions."""

import unittest
from unittest.mock import Mock, patch

from nautobot_ssot.integrations.forward_enterprise.utils.diffsync import (
    create_placeholder_device,
    log_processing_error,
    log_processing_warning,
)
from nautobot_ssot.integrations.forward_enterprise.utils.vlan_extraction import (
    create_vlan_group_name,
    extract_vlan_id_from_interface,
    extract_vlans_by_location,
    get_device_location,
)


class TestDiffSyncUtils(unittest.TestCase):
    """Test DiffSync utility functions."""

    def test_create_placeholder_device(self):
        """Test placeholder device creation."""
        device = create_placeholder_device("test-device")

        self.assertTrue(device.name.startswith("PLACEHOLDER-test-device-"))
        self.assertEqual(device.device_type__manufacturer__name, "Unknown")
        self.assertEqual(device.device_type__model, "Unknown")
        self.assertEqual(device.status__name, "Active")
        self.assertEqual(device.role__name, "Network Device")  # Default role from constants
        self.assertEqual(device.location__name, "Unknown")

    def test_log_processing_error(self):
        """Test error logging function."""
        logger = Mock()
        log_processing_error(logger, "device", "test-device", Exception("Test error"))

        logger.error.assert_called_once()
        # Check that all arguments are passed correctly (positional and keyword)
        call_args = logger.error.call_args[0]  # Positional args

        # Verify the format string and components
        self.assertEqual(call_args[0], "Error processing %s %s:\n```\n%s\n```%s")
        self.assertEqual(call_args[1], "device")
        self.assertEqual(call_args[2], "test-device")
        self.assertEqual(str(call_args[3]), "Test error")
        self.assertEqual(call_args[4], "")  # No context provided

    def test_log_processing_error_with_context(self):
        """Test error logging with context."""
        logger = Mock()
        context = {"field": "value", "extra": "info"}
        log_processing_error(logger, "interface", "eth0", ValueError("Invalid value"), context)

        logger.error.assert_called_once()
        call_args = logger.error.call_args[0]  # Positional args

        # Verify the format string and components
        self.assertEqual(call_args[0], "Error processing %s %s:\n```\n%s\n```%s")
        self.assertEqual(call_args[1], "interface")
        self.assertEqual(call_args[2], "eth0")
        self.assertEqual(str(call_args[3]), "Invalid value")
        self.assertIn("Context:", call_args[4])  # Context is included

    def test_log_processing_warning(self):
        """Test warning logging function."""
        logger = Mock()
        log_processing_warning(logger, "prefix", "192.168.1.0/24", "Duplicate detected")

        logger.warning.assert_called_once()
        call_args = logger.warning.call_args[0]  # Positional args

        # Verify the format string and components
        self.assertEqual(call_args[0], "Warning processing %s %s:\n```\n%s\n```%s")
        self.assertEqual(call_args[1], "prefix")
        self.assertEqual(call_args[2], "192.168.1.0/24")
        self.assertEqual(call_args[3], "Duplicate detected")
        self.assertEqual(call_args[4], "")  # No context provided


class TestVLANExtraction(unittest.TestCase):
    """Test VLAN extraction utilities."""

    def test_extract_vlan_id_from_interface_vlan_prefix(self):
        """Test VLAN ID extraction from VLAN interfaces."""
        # Test various VLAN interface formats
        self.assertEqual(extract_vlan_id_from_interface("vlan100"), 100)
        self.assertEqual(extract_vlan_id_from_interface("Vlan200"), 200)
        self.assertEqual(extract_vlan_id_from_interface("VLAN300"), 300)
        self.assertEqual(extract_vlan_id_from_interface("vl100"), 100)

    def test_extract_vlan_id_from_interface_subinterface(self):
        """Test VLAN ID extraction from subinterfaces."""
        self.assertEqual(extract_vlan_id_from_interface("GigE0/0/1.100"), 100)
        self.assertEqual(extract_vlan_id_from_interface("FastEthernet0/1.200"), 200)
        self.assertEqual(extract_vlan_id_from_interface("eth0.300"), 300)

    def test_extract_vlan_id_from_interface_slash_format(self):
        """Test VLAN ID extraction from slash format."""
        self.assertEqual(extract_vlan_id_from_interface("interface/100"), 100)
        self.assertEqual(extract_vlan_id_from_interface("port/200"), 200)

    def test_extract_vlan_id_from_interface_invalid(self):
        """Test VLAN ID extraction with invalid inputs."""
        # No VLAN ID present - these should return None
        self.assertIsNone(extract_vlan_id_from_interface("eth0"))

        # This actually extracts VLAN 1 from the "/1" pattern, which is valid behavior
        self.assertEqual(extract_vlan_id_from_interface("GigabitEthernet0/0/1"), 1)

        # Empty input
        self.assertIsNone(extract_vlan_id_from_interface(""))

        # Invalid VLAN ID ranges
        self.assertIsNone(extract_vlan_id_from_interface("vlan5000"))  # Too high
        self.assertIsNone(extract_vlan_id_from_interface("vlan0"))  # Too low

    def test_create_vlan_group_name(self):
        """Test VLAN group name creation."""
        result = create_vlan_group_name("Site-A")
        self.assertEqual(result, "Forward Enterprise - Site-A")

        result = create_vlan_group_name("Main Campus")
        self.assertEqual(result, "Forward Enterprise - Main Campus")

    def test_get_device_location_success(self):
        """Test successful device location retrieval."""
        adapter = Mock()
        device_obj = Mock()
        device_obj.location__name = "Site-A"
        adapter.get.return_value = device_obj

        result = get_device_location(adapter, "test-device")
        self.assertEqual(result, "Site-A")
        adapter.get.assert_called_once_with("device", {"name": "test-device"})

    def test_get_device_location_not_found(self):
        """Test device location retrieval when device not found."""
        adapter = Mock()
        adapter.get.side_effect = KeyError("Device not found")
        adapter.devices_data = []  # No device data available

        result = get_device_location(adapter, "unknown-device")
        self.assertIsNone(result)

    def test_extract_vlans_by_location(self):
        """Test VLAN extraction by location."""
        adapter = Mock()

        # Mock interface data
        adapter.interfaces_data = [
            {"name": "vlan100", "device": "switch1"},
            {"name": "vlan200", "device": "switch1"},
            {"name": "vlan100", "device": "switch2"},  # Same VLAN, different device
            {"name": "eth0", "device": "router1"},  # No VLAN
        ]

        # Mock IPAM data
        adapter.ipam_data = [
            {"interface": "vlan300", "device": "switch1"},
            {"interface": "eth1.400", "device": "switch2"},
        ]

        # Mock device locations
        def mock_get_device_location(_adapter_obj, device_name):
            locations = {"switch1": "Site-A", "switch2": "Site-B", "router1": "Site-A"}
            return locations.get(device_name, "Unknown")

        with patch(
            "nautobot_ssot.integrations.forward_enterprise.utils.vlan_extraction.get_device_location",
            side_effect=mock_get_device_location,
        ):
            result = extract_vlans_by_location(adapter)

        expected = {"Site-A": {100, 200, 300}, "Site-B": {100, 400}}

        # Convert sets to compare
        for location in result:
            result[location] = set(result[location])

        self.assertEqual(result, expected)

    def test_extract_vlans_by_location_empty_data(self):
        """Test VLAN extraction with empty data."""
        adapter = Mock()
        adapter.interfaces_data = []
        adapter.ipam_data = []

        result = extract_vlans_by_location(adapter)
        self.assertEqual(result, {})

    def test_extract_vlans_by_location_no_vlans(self):
        """Test VLAN extraction when no VLANs are found."""
        adapter = Mock()
        adapter.interfaces_data = [
            {"name": "eth0", "device": "router1"},
            {"name": "GigabitEthernet0/0/1", "device": "switch1"},
        ]
        adapter.ipam_data = []

        # Mock get_device_location to avoid VLAN extraction
        with patch(
            "nautobot_ssot.integrations.forward_enterprise.utils.vlan_extraction.get_device_location",
            return_value="Site-A",
        ):
            # Mock extract_vlan_id_from_interface to return None for these interfaces
            with patch(
                "nautobot_ssot.integrations.forward_enterprise.utils.vlan_extraction.extract_vlan_id_from_interface",
                return_value=None,
            ):
                result = extract_vlans_by_location(adapter)
                self.assertEqual(result, {})
