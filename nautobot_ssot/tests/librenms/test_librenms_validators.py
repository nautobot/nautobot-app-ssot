"""Unit tests for LibreNMS utility functions."""

import os
from unittest.mock import MagicMock, patch

from django.test import TestCase
from parameterized import parameterized

from nautobot_ssot.integrations.librenms.utils import (
    check_sor_field,
    get_sor_field_nautobot_object,
    has_required_values,
    is_running_tests,
    normalize_device_hostname,
    normalize_gps_coordinates,
    normalize_setting,
)


class TestNormalizeGPSCoordinates(TestCase):
    """Test GPS coordinate normalization."""

    @parameterized.expand(
        [
            ("float_coordinates", 41.874677429096174, 41.874677),
            ("string_coordinates", "41.874677429096174", 41.874677),
            ("already_rounded", 41.874677, 41.874677),
            ("negative_coordinates", -87.62672768379687, -87.626728),
        ]
    )
    def test_normalize_gps_coordinates(self, _test_name, input_value, expected_result):
        """Test normalizing GPS coordinates with various input types."""
        result = normalize_gps_coordinates(input_value)
        self.assertEqual(result, expected_result)


class TestNormalizeSetting(TestCase):
    """Test setting normalization."""

    @patch("nautobot_ssot.integrations.librenms.utils.settings")
    @patch("nautobot_ssot.integrations.librenms.utils.constance_name")
    def test_normalize_setting_from_plugins_config(self, mock_constance, mock_settings):
        """Test getting setting from plugins config."""
        mock_settings.PLUGINS_CONFIG = {"nautobot_ssot": {"test_setting": "plugin_value"}}
        mock_constance.TEST_SETTING = "constance_value"

        result = normalize_setting("test_setting")
        self.assertEqual(result, "plugin_value")

    @patch("nautobot_ssot.integrations.librenms.utils.settings")
    @patch("nautobot_ssot.integrations.librenms.utils.constance_name")
    def test_normalize_setting_from_constance(self, mock_constance, mock_settings):
        """Test getting setting from constance when not in plugins config."""
        mock_settings.PLUGINS_CONFIG = {"nautobot_ssot": {}}
        mock_constance.TEST_SETTING = "constance_value"

        result = normalize_setting("test_setting")
        self.assertEqual(result, "constance_value")

    @patch("nautobot_ssot.integrations.librenms.utils.settings")
    @patch("nautobot_ssot.integrations.librenms.utils.constance_name")
    def test_normalize_setting_case_insensitive(self, mock_constance, mock_settings):
        """Test that setting lookup is case insensitive."""
        mock_settings.PLUGINS_CONFIG = {"nautobot_ssot": {"test_setting": "plugin_value"}}
        mock_constance.TEST_SETTING = "constance_value"

        result = normalize_setting("TEST_SETTING")
        self.assertEqual(result, "plugin_value")


class TestNormalizeDeviceHostname(TestCase):
    """Test device hostname normalization."""

    def setUp(self):
        """Set up test case."""
        self.job = MagicMock()
        self.job.hostname_field = "hostname"

    @parameterized.expand(
        [
            ("domain_name", "router.example.com", "ROUTER"),
            ("simple_name", "router", "ROUTER"),
            ("mixed_case", "Router.Example.COM", "ROUTER"),
        ]
    )
    def test_normalize_device_hostname_domain_name(self, _test_name, input_value, expected_result):
        """Test normalizing domain name hostname."""
        device = {"hostname": input_value}

        result = normalize_device_hostname(device, self.job)
        self.assertEqual(result, expected_result)


class TestHasRequiredValues(TestCase):
    """Test required values validation."""

    def setUp(self):
        """Set up test case."""
        self.job = MagicMock()
        self.job.hostname_field = "hostname"
        self.job.unpermitted_values = None
        self.job.default_role.name = "network"

    def test_has_required_values_all_present(self):
        """Test when all required values are present."""
        device = {
            "hostname": "test-device",
            "location": "test-location",
            "role": "test-role",
            "platform": "ios",
            "device_type": "cisco-ios",
        }

        result = has_required_values(device, self.job)

        # Check that all fields are valid
        self.assertTrue(result["hostname"]["valid"])
        self.assertTrue(result["location"]["valid"])
        self.assertTrue(result["role"]["valid"])
        self.assertTrue(result["platform"]["valid"])
        self.assertTrue(result["device_type"]["valid"])

    def test_has_required_values_missing_hostname(self):
        """Test when hostname is missing."""
        device = {
            "hostname": None,  # Missing hostname
            "location": "test-location",
            "role": "network",
            "platform": "ios",
            "device_type": "cisco-ios",
        }

        result = has_required_values(device, self.job)

        # Check that hostname is invalid
        self.assertFalse(result["hostname"]["valid"])
        self.assertEqual(result["hostname"]["reason"], "String is required")

        # Other fields should still be valid
        self.assertTrue(result["location"]["valid"])
        self.assertTrue(result["role"]["valid"])
        self.assertTrue(result["platform"]["valid"])
        self.assertTrue(result["device_type"]["valid"])

    def test_has_required_values_empty_hostname(self):
        """Test when hostname is empty."""
        device = {
            "hostname": "",
            "location": "test-location",
            "role": "network",
            "platform": "ios",
            "device_type": "cisco-ios",
        }

        result = has_required_values(device, self.job)

        # Check that hostname is invalid
        self.assertFalse(result["hostname"]["valid"])
        self.assertEqual(result["hostname"]["reason"], "String is required")

    @parameterized.expand(
        [
            ("allowed_ip_v4", "192.168.1.1", True),
            ("allowed_ip_v6", "2001:db8::1", True),
        ]
    )
    @patch("nautobot_ssot.integrations.librenms.utils.settings")
    def test_has_required_values_hostname_is_ip_address_allowed(
        self, _test_name, input_value, expected_result, mock_settings
    ):
        """Test when hostname is an IP address."""
        mock_settings.PLUGINS_CONFIG = {"nautobot_ssot": {"librenms_allow_ip_hostnames": True}}
        device = {
            "hostname": input_value,
            "location": "test-location",
            "role": "network",
            "platform": "ios",
            "device_type": "cisco-ios",
        }

        result = has_required_values(device, self.job)

        # Check that hostname is invalid
        self.assertEqual(result["hostname"]["valid"], expected_result)

    @parameterized.expand(
        [
            ("not_allowed_ip_v4", "192.168.1.1", False, "The hostname cannot be an IP Address"),
            ("not_allowed_ip_v6", "2001:db8::1:1", False, "The hostname cannot be an IP Address"),
        ]
    )
    @patch("nautobot_ssot.integrations.librenms.utils.settings")
    def test_has_required_values_hostname_is_ip_address_not_allowed(
        self,
        _test_name,
        input_value,
        expected_result,  # pylint: disable=unused-argument
        expected_reason,
        mock_settings,
    ):
        """Test when hostname is an IP address and not allowed."""
        mock_settings.PLUGINS_CONFIG = {"nautobot_ssot": {"librenms_allow_ip_hostnames": False}}
        device = {
            "hostname": input_value,
            "location": "test-location",
            "role": "network",
            "platform": "ios",
            "device_type": "cisco-ios",
        }

        result = has_required_values(device, self.job)

        # Check that hostname is invalid
        self.assertFalse(result["hostname"]["valid"])
        self.assertEqual(result["hostname"]["reason"], expected_reason)

    def test_has_required_values_multiple_missing(self):
        """Test when multiple required values are missing."""
        device = {
            "hostname": "test-device",
            "location": "",
            "role": None,
            "platform": "ios",
            "device_type": "cisco-ios",
        }

        result = has_required_values(device, self.job)

        # Check that location and role are invalid
        self.assertFalse(result["location"]["valid"])
        self.assertEqual(result["location"]["reason"], "String is required")
        self.assertFalse(result["role"]["valid"])
        self.assertEqual(result["role"]["reason"], "String is required")

        # Other fields should still be valid
        self.assertTrue(result["hostname"]["valid"])
        self.assertTrue(result["platform"]["valid"])
        self.assertTrue(result["device_type"]["valid"])

    def test_has_required_values_unpermitted_values(self):
        """Test when device has unpermitted values."""
        self.job.unpermitted_values = ["forbidden-role"]
        device = {
            "hostname": "test-device",
            "location": "test-location",
            "role": "forbidden-role",
            "platform": "ios",
            "device_type": "cisco-ios",
        }

        result = has_required_values(device, self.job)

        # Check that role is invalid due to unpermitted value
        self.assertFalse(result["role"]["valid"])
        self.assertEqual(result["role"]["reason"], "role cannot be 'forbidden-role'")

    def test_has_required_values_manufacturer_mapping_missing(self):
        """Test when manufacturer mapping is missing for platform."""
        device = {
            "hostname": "test-device",
            "location": "test-location",
            "role": "network",
            "platform": "unknown-os",  # OS not in os_manufacturer_map
            "device_type": "cisco-ios",
        }

        result = has_required_values(device, self.job)

        # Check that platform is invalid due to missing manufacturer mapping
        self.assertFalse(result["platform"]["valid"])
        self.assertEqual(result["platform"]["reason"], "Manufacturer mapping not found for OS: unknown-os")

    def test_has_required_values_manufacturer_mapping_exists(self):
        """Test when manufacturer mapping exists for platform."""
        device = {
            "hostname": "test-device",
            "location": "test-location",
            "role": "network",
            "platform": "ios",  # OS that exists in os_manufacturer_map
            "device_type": "cisco-ios",
        }

        result = has_required_values(device, self.job)

        # Check that platform is valid
        self.assertTrue(result["platform"]["valid"])

    def test_has_required_values_platform_empty(self):
        """Test when platform is empty."""
        device = {
            "hostname": "test-device",
            "location": "test-location",
            "role": "network",
            "platform": "",
            "device_type": "cisco-ios",
        }

        result = has_required_values(device, self.job)

        # Check that platform is invalid due to empty string
        self.assertFalse(result["platform"]["valid"])
        self.assertEqual(result["platform"]["reason"], "String is required")

    def test_has_required_values_platform_none(self):
        """Test when platform is None."""
        device = {
            "hostname": "test-device",
            "location": "test-location",
            "role": "network",
            "platform": None,
            "device_type": "cisco-ios",
        }

        result = has_required_values(device, self.job)

        # Check that platform is invalid due to None value
        self.assertFalse(result["platform"]["valid"])
        self.assertEqual(result["platform"]["reason"], "String is required")


class TestCheckSorField(TestCase):
    """Test System of Record field checking."""

    def setUp(self):
        """Set up test case."""
        self.model = MagicMock()
        self.model.custom_field_data = {}

    def test_check_sor_field_present_and_correct(self):
        """Test when SOR field is present and set to LibreNMS."""
        self.model.custom_field_data = {"system_of_record": "LibreNMS"}

        result = check_sor_field(self.model)
        self.assertTrue(result)

    def test_check_sor_field_present_but_wrong_value(self):
        """Test when SOR field is present but has wrong value."""
        self.model.custom_field_data = {"system_of_record": "OtherSystem"}

        result = check_sor_field(self.model)
        self.assertFalse(result)

    def test_check_sor_field_not_present(self):
        """Test when SOR field is not present."""
        result = check_sor_field(self.model)
        self.assertFalse(result)

    def test_check_sor_field_none_value(self):
        """Test when SOR field is None."""
        self.model.custom_field_data = {"system_of_record": None}

        result = check_sor_field(self.model)
        self.assertFalse(result)

    @patch.dict(os.environ, {"NAUTOBOT_SSOT_LIBRENMS_SYSTEM_OF_RECORD": "CustomSystem"})
    def test_check_sor_field_custom_system_of_record(self):
        """Test with custom system of record from environment."""
        self.model.custom_field_data = {"system_of_record": "CustomSystem"}

        result = check_sor_field(self.model)
        self.assertTrue(result)


class TestGetSorFieldNautobotObject(TestCase):
    """Test getting System of Record field from Nautobot object."""

    def setUp(self):
        """Set up test case."""
        self.nb_object = MagicMock()
        self.nb_object.custom_field_data = {}

    def test_get_sor_field_nautobot_object_present(self):
        """Test when SOR field is present."""
        self.nb_object.custom_field_data = {"system_of_record": "LibreNMS"}

        result = get_sor_field_nautobot_object(self.nb_object)
        self.assertEqual(result, "LibreNMS")

    def test_get_sor_field_nautobot_object_not_present(self):
        """Test when SOR field is not present."""
        result = get_sor_field_nautobot_object(self.nb_object)
        self.assertEqual(result, "")

    def test_get_sor_field_nautobot_object_none_value(self):
        """Test when SOR field is None."""
        self.nb_object.custom_field_data = {"system_of_record": None}

        result = get_sor_field_nautobot_object(self.nb_object)
        self.assertEqual(result, "")


class TestIsRunningTests(TestCase):
    """Test detection of running tests."""

    def test_is_running_tests_in_test_environment(self):
        """Test when running in test environment."""
        result = is_running_tests()
        # This should be True when running in a test environment
        self.assertTrue(result)

    @patch("nautobot_ssot.integrations.librenms.utils.inspect.stack")
    def test_is_running_tests_not_in_test_environment(self, mock_stack):
        """Test when not running in test environment."""
        # Mock the stack to not contain unittest/case.py
        mock_stack.return_value = [MagicMock(filename="/some/other/file.py"), MagicMock(filename="/another/file.py")]

        result = is_running_tests()
        self.assertFalse(result)

    @patch("nautobot_ssot.integrations.librenms.utils.inspect.stack")
    def test_is_running_tests_with_unittest_in_stack(self, mock_stack):
        """Test when unittest/case.py is in the stack."""
        # Mock the stack to contain unittest/case.py
        mock_stack.return_value = [
            MagicMock(filename="/some/other/file.py"),
            MagicMock(filename="/path/to/unittest/case.py"),
            MagicMock(filename="/another/file.py"),
        ]

        result = is_running_tests()
        self.assertTrue(result)
