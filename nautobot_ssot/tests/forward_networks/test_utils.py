"""Tests for Forward Networks utilities."""

import unittest
from unittest.mock import Mock, patch

from nautobot_ssot.integrations.forward_networks.utils import (
    extract_ip_from_string,
    get_interface_type_from_name,
    normalize_device_name,
    normalize_interface_name,
    parse_forward_networks_device_role,
    sanitize_custom_fields,
    validate_mac_address,
)


class TestForwardNetworksUtils(unittest.TestCase):
    """Test Forward Networks utility functions."""

    def test_normalize_device_name(self):
        """Test device name normalization."""
        # Test basic normalization
        self.assertEqual(normalize_device_name("test device"), "test-device")
        self.assertEqual(normalize_device_name("Test-Device-01"), "Test-Device-01")
        self.assertEqual(normalize_device_name("device@#$%name"), "device-name")  # Multiple special chars become single hyphen
        self.assertEqual(normalize_device_name("---device---"), "device")

        # Test special characters
        self.assertEqual(normalize_device_name("device.example.com"), "device.example.com")
        self.assertEqual(normalize_device_name("device_name_01"), "device_name_01")

    def test_normalize_interface_name(self):
        """Test interface name normalization."""
        # Test Gigabit Ethernet
        self.assertEqual(normalize_interface_name("Gi1/0/1"), "GigabitEthernet1/0/1")
        self.assertEqual(normalize_interface_name("gi2/1"), "GigabitEthernet2/1")

        # Test Ten Gigabit Ethernet
        self.assertEqual(normalize_interface_name("Te1/0/1"), "TenGigabitEthernet1/0/1")
        self.assertEqual(normalize_interface_name("te0/1"), "TenGigabitEthernet0/1")

        # Test Forty Gigabit Ethernet
        self.assertEqual(normalize_interface_name("Fo1/0/1"), "FortyGigabitEthernet1/0/1")

        # Test Hundred Gigabit Ethernet
        self.assertEqual(normalize_interface_name("Hu1/0/1"), "HundredGigE1/0/1")

        # Test case insensitive
        self.assertEqual(normalize_interface_name("GI1/0/1"), "GigabitEthernet1/0/1")

        # Test no change for already normalized
        self.assertEqual(normalize_interface_name("GigabitEthernet1/0/1"), "GigabitEthernet1/0/1")

    def test_parse_forward_networks_device_role(self):
        """Test device role parsing."""
        # Test firewall detection
        self.assertEqual(parse_forward_networks_device_role("firewall", "fw-01"), "firewall")
        self.assertEqual(parse_forward_networks_device_role("asa", "border-fw"), "firewall")
        self.assertEqual(parse_forward_networks_device_role("palo-alto", "pa-220"), "firewall")

        # Test router detection
        self.assertEqual(parse_forward_networks_device_role("router", "rtr-01"), "router")
        self.assertEqual(parse_forward_networks_device_role("asr", "border-rtr"), "router")

        # Test switch detection
        self.assertEqual(parse_forward_networks_device_role("switch", "core-sw"), "distribution")
        self.assertEqual(parse_forward_networks_device_role("nexus", "dist-switch"), "distribution")
        self.assertEqual(parse_forward_networks_device_role("catalyst", "access-sw"), "access")
        self.assertEqual(parse_forward_networks_device_role("switch", "regular-switch"), "switch")

        # Test load balancer detection
        self.assertEqual(parse_forward_networks_device_role("f5", "lb-01"), "load-balancer")
        self.assertEqual(parse_forward_networks_device_role("netscaler", "citrix-lb"), "load-balancer")

        # Test wireless controller
        self.assertEqual(parse_forward_networks_device_role("wlc", "wireless-controller"), "wireless-controller")
        self.assertEqual(parse_forward_networks_device_role("wifi", "ap-controller"), "wireless-controller")

        # Test default
        self.assertEqual(parse_forward_networks_device_role("unknown", "device"), "access")
        self.assertEqual(parse_forward_networks_device_role(None, None), "access")

    def test_sanitize_custom_fields(self):
        """Test custom fields sanitization."""
        # Test basic sanitization
        input_fields = {
            "field name": "value1",
            "field@#$": "value2",
            "normal_field": "value3",
            "Field-With-Dashes": "value4",
        }

        result = sanitize_custom_fields(input_fields)

        self.assertTrue("field_name" in result)
        self.assertTrue("field" in result)  # Special characters stripped from edges
        self.assertTrue("normal_field" in result)
        self.assertTrue("field_with_dashes" in result)

        # Test value types
        complex_fields = {
            "string_field": "text",
            "int_field": 42,
            "float_field": 3.14,
            "bool_field": True,
            "list_field": [1, 2, 3],
            "dict_field": {"nested": "value"},
            "object_field": Mock(),  # Non-JSON serializable
        }

        result = sanitize_custom_fields(complex_fields)

        self.assertEqual(result["string_field"], "text")
        self.assertEqual(result["int_field"], 42)
        self.assertEqual(result["float_field"], 3.14)
        self.assertTrue(result["bool_field"])
        self.assertEqual(result["list_field"], [1, 2, 3])
        self.assertEqual(result["dict_field"], {"nested": "value"})
        self.assertTrue(isinstance(result["object_field"], str))

        # Test empty/None input
        self.assertEqual(sanitize_custom_fields(None), {})
        self.assertEqual(sanitize_custom_fields({}), {})

    def test_extract_ip_from_string(self):
        """Test IP address extraction."""
        # Test with CIDR notation
        self.assertEqual(extract_ip_from_string("192.168.1.1/24"), "192.168.1.1")
        self.assertEqual(extract_ip_from_string("10.0.0.1/8"), "10.0.0.1")

        # Test without CIDR
        self.assertEqual(extract_ip_from_string("192.168.1.1"), "192.168.1.1")

        # Test edge cases
        self.assertIsNone(extract_ip_from_string(None))
        self.assertIsNone(extract_ip_from_string(""))
        self.assertEqual(extract_ip_from_string("not-an-ip"), "not-an-ip")

    def test_validate_mac_address(self):
        """Test MAC address validation."""
        # Test valid MAC addresses
        self.assertEqual(validate_mac_address("00:1A:2B:3C:4D:5E"), "00:1a:2b:3c:4d:5e")
        self.assertEqual(validate_mac_address("00-1A-2B-3C-4D-5E"), "00:1a:2b:3c:4d:5e")
        self.assertEqual(validate_mac_address("001A2B3C4D5E"), "00:1a:2b:3c:4d:5e")
        self.assertEqual(validate_mac_address("001a2b3c4d5e"), "00:1a:2b:3c:4d:5e")

        # Test invalid MAC addresses
        self.assertIsNone(validate_mac_address("00:1A:2B:3C:4D"))  # Too short
        self.assertIsNone(validate_mac_address("00:1A:2B:3C:4D:5E:FF"))  # Too long
        self.assertIsNone(validate_mac_address("ZZ:1A:2B:3C:4D:5E"))  # Invalid characters
        self.assertIsNone(validate_mac_address(""))
        self.assertIsNone(validate_mac_address(None))

    def test_get_interface_type_from_name(self):
        """Test interface type detection from name."""
        # Test Gigabit Ethernet
        self.assertEqual(get_interface_type_from_name("GigabitEthernet1/0/1"), "1000base-t")
        self.assertEqual(get_interface_type_from_name("Gi1/0/1"), "1000base-t")
        self.assertEqual(get_interface_type_from_name("gigabit0/1"), "1000base-t")

        # Test Ten Gigabit Ethernet
        self.assertEqual(get_interface_type_from_name("TenGigabitEthernet1/0/1"), "10gbase-x-sfpp")
        self.assertEqual(get_interface_type_from_name("Te1/0/1"), "10gbase-x-sfpp")
        self.assertEqual(get_interface_type_from_name("tengig0/1"), "10gbase-x-sfpp")

        # Test Forty Gigabit Ethernet
        self.assertEqual(get_interface_type_from_name("FortyGigabitEthernet1/0/1"), "40gbase-x-qsfpp")
        self.assertEqual(get_interface_type_from_name("Fo1/0/1"), "40gbase-x-qsfpp")

        # Test Hundred Gigabit Ethernet
        self.assertEqual(get_interface_type_from_name("HundredGigE1/0/1"), "100gbase-x-qsfp28")
        self.assertEqual(get_interface_type_from_name("Hu1/0/1"), "100gbase-x-qsfp28")

        # Test Fast Ethernet
        self.assertEqual(get_interface_type_from_name("FastEthernet0/1"), "100base-tx")
        self.assertEqual(get_interface_type_from_name("Fa0/1"), "100base-tx")
        self.assertEqual(get_interface_type_from_name("ethernet0/1"), "100base-tx")

        # Test Virtual interfaces
        self.assertEqual(get_interface_type_from_name("Loopback0"), "virtual")
        self.assertEqual(get_interface_type_from_name("Vlan100"), "virtual")
        self.assertEqual(get_interface_type_from_name("Tunnel0"), "virtual")

        # Test Management interfaces
        self.assertEqual(get_interface_type_from_name("Management0/0"), "1000base-t")
        self.assertEqual(get_interface_type_from_name("mgmt0"), "1000base-t")

        # Test unknown/other
        self.assertEqual(get_interface_type_from_name("UnknownInterface"), "other")
        self.assertEqual(get_interface_type_from_name("Serial0/0/0"), "other")


@patch("nautobot_ssot.integrations.forward_networks.utils.Manufacturer")
@patch("nautobot_ssot.integrations.forward_networks.utils.DeviceType")
@patch("nautobot_ssot.integrations.forward_networks.utils.Platform")
@patch("nautobot_ssot.integrations.forward_networks.utils.Status")
@patch("nautobot_ssot.integrations.forward_networks.utils.Tag")
@patch("nautobot_ssot.integrations.forward_networks.utils.Namespace")
class TestForwardNetworksUtilsWithMocks:
    """Test utility functions that interact with Nautobot models."""

    def test_get_or_create_manufacturer(
        self, mock_namespace, mock_tag, mock_status, mock_platform, mock_device_type, mock_manufacturer
    ):
        """Test manufacturer creation/retrieval."""
        from nautobot_ssot.integrations.forward_networks.utils import get_or_create_manufacturer

        # Mock the get_or_create method
        mock_manufacturer.objects.get_or_create.return_value = (Mock(name="Cisco"), True)

        result = get_or_create_manufacturer("Cisco")

        mock_manufacturer.objects.get_or_create.assert_called_once_with(
            name="Cisco", defaults={"description": "Manufacturer imported from Forward Networks"}
        )
        self.assertEqual(result.name, "Cisco")

    def test_get_or_create_device_type(
        self, mock_namespace, mock_tag, mock_status, mock_platform, mock_device_type, mock_manufacturer
    ):
        """Test device type creation/retrieval."""
        from nautobot_ssot.integrations.forward_networks.utils import get_or_create_device_type

        mock_manufacturer_obj = Mock(name="Cisco")
        mock_device_type.objects.get_or_create.return_value = (Mock(model="Nexus 9000"), True)

        result = get_or_create_device_type(mock_manufacturer_obj, "Nexus 9000")

        mock_device_type.objects.get_or_create.assert_called_once_with(
            model="Nexus 9000",
            manufacturer=mock_manufacturer_obj,
            defaults={
                "description": "Device type imported from Forward Networks",
                "u_height": 1,
            },
        )
        self.assertEqual(result.model, "Nexus 9000")

    def test_get_or_create_tag(
        self, mock_namespace, mock_tag, mock_status, mock_platform, mock_device_type, mock_manufacturer
    ):
        """Test tag creation/retrieval."""
        from nautobot_ssot.integrations.forward_networks.utils import get_or_create_tag

        mock_tag.objects.get_or_create.return_value = (Mock(name="test-tag"), True)

        result = get_or_create_tag("test-tag")

        mock_tag.objects.get_or_create.assert_called_once_with(
            name="test-tag", defaults={"description": "Tag imported from Forward Networks"}
        )
        self.assertEqual(result.name, "test-tag")

    def test_create_forward_networks_tag(
        self, mock_namespace, mock_tag, mock_status, mock_platform, mock_device_type, mock_manufacturer
    ):
        """Test creation of Forward Networks sync tag."""
        from nautobot_ssot.integrations.forward_networks.utils import create_forward_networks_tag

        mock_tag.objects.get_or_create.return_value = (Mock(name="SSoT Synced from Forward Networks"), True)

        result = create_forward_networks_tag()

        mock_tag.objects.get_or_create.assert_called_once_with(
            name="SSoT Synced from Forward Networks",
            defaults={"description": "Objects synchronized from Forward Networks", "color": "2196f3"},
        )
        self.assertEqual(result.name, "SSoT Synced from Forward Networks")
