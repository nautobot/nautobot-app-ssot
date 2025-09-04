"""Unit tests for LibreNMS utility functions."""

import inspect
import ipaddress
import os
from unittest.mock import MagicMock, patch

from django.conf import settings
from django.core.exceptions import ValidationError
from django.test import TestCase
from nautobot.core.testing import TransactionTestCase
from nautobot.dcim.models.devices import DeviceType, Manufacturer, Platform
from nautobot.dcim.models.locations import Location, LocationType
from nautobot.extras.models.roles import Role

from nautobot_ssot.integrations.librenms.utils import (
    check_sor_field,
    get_sor_field_nautobot_object,
    has_required_values,
    has_valid_device_type,
    has_valid_location_data,
    has_valid_manufacturer_data,
    has_valid_platform,
    has_valid_role,
    is_running_tests,
    normalize_device_hostname,
    normalize_gps_coordinates,
    normalize_setting,
    validate_device_data,
)


class TestNormalizeGPSCoordinates(TestCase):
    """Test GPS coordinate normalization."""

    def test_normalize_gps_coordinates_float(self):
        """Test normalizing float GPS coordinates."""
        result = normalize_gps_coordinates(41.874677429096174)
        self.assertEqual(result, 41.874677)

    def test_normalize_gps_coordinates_string(self):
        """Test normalizing string GPS coordinates."""
        result = normalize_gps_coordinates("41.874677429096174")
        self.assertEqual(result, 41.874677)

    def test_normalize_gps_coordinates_already_rounded(self):
        """Test normalizing already rounded coordinates."""
        result = normalize_gps_coordinates(41.874677)
        self.assertEqual(result, 41.874677)

    def test_normalize_gps_coordinates_negative(self):
        """Test normalizing negative coordinates."""
        result = normalize_gps_coordinates(-87.62672768379687)
        self.assertEqual(result, -87.626728)


class TestNormalizeSetting(TestCase):
    """Test setting normalization."""

    @patch("nautobot_ssot.integrations.librenms.utils.settings")
    @patch("nautobot_ssot.integrations.librenms.utils.constance_name")
    def test_normalize_setting_from_plugins_config(self, mock_constance, mock_settings):
        """Test getting setting from plugins config."""
        mock_settings.PLUGINS_CONFIG = {
            "nautobot_ssot": {
                "test_setting": "plugin_value"
            }
        }
        mock_constance.TEST_SETTING = "constance_value"

        result = normalize_setting("test_setting")
        self.assertEqual(result, "plugin_value")

    @patch("nautobot_ssot.integrations.librenms.utils.settings")
    @patch("nautobot_ssot.integrations.librenms.utils.constance_name")
    def test_normalize_setting_from_constance(self, mock_constance, mock_settings):
        """Test getting setting from constance when not in plugins config."""
        mock_settings.PLUGINS_CONFIG = {
            "nautobot_ssot": {}
        }
        mock_constance.TEST_SETTING = "constance_value"

        result = normalize_setting("test_setting")
        self.assertEqual(result, "constance_value")

    @patch("nautobot_ssot.integrations.librenms.utils.settings")
    @patch("nautobot_ssot.integrations.librenms.utils.constance_name")
    def test_normalize_setting_case_insensitive(self, mock_constance, mock_settings):
        """Test that setting lookup is case insensitive."""
        mock_settings.PLUGINS_CONFIG = {
            "nautobot_ssot": {
                "test_setting": "plugin_value"
            }
        }
        mock_constance.TEST_SETTING = "constance_value"

        result = normalize_setting("TEST_SETTING")
        self.assertEqual(result, "plugin_value")


class TestNormalizeDeviceHostname(TestCase):
    """Test device hostname normalization."""

    def setUp(self):
        """Set up test case."""
        self.job = MagicMock()
        self.job.hostname_field = "hostname"

    @patch("nautobot_ssot.integrations.librenms.utils.settings")
    def test_normalize_device_hostname_ip_address_allowed(self, mock_settings):
        """Test normalizing IP address hostname when allowed."""
        mock_settings.PLUGINS_CONFIG = {
            "nautobot_ssot": {
                "librenms_allow_ip_hostnames": True
            }
        }
        device = {"hostname": "192.168.1.1"}

        result = normalize_device_hostname(device, self.job)
        self.assertEqual(result, "192.168.1.1")

    @patch("nautobot_ssot.integrations.librenms.utils.settings")
    def test_normalize_device_hostname_ip_address_not_allowed(self, mock_settings):
        """Test normalizing IP address hostname when not allowed."""
        mock_settings.PLUGINS_CONFIG = {
            "nautobot_ssot": {
                "librenms_allow_ip_hostnames": False
            }
        }
        device = {"hostname": "192.168.1.1", "load_errors": []}

        result = normalize_device_hostname(device, self.job)
        self.assertIsNone(result)
        self.assertIn("The hostname cannot be an IP Address", device["load_errors"])

    def test_normalize_device_hostname_domain_name(self):
        """Test normalizing domain name hostname."""
        device = {"hostname": "router.example.com"}

        result = normalize_device_hostname(device, self.job)
        self.assertEqual(result, "ROUTER")

    def test_normalize_device_hostname_simple_name(self):
        """Test normalizing simple hostname."""
        device = {"hostname": "router"}

        result = normalize_device_hostname(device, self.job)
        self.assertEqual(result, "ROUTER")

    def test_normalize_device_hostname_mixed_case(self):
        """Test normalizing mixed case hostname."""
        device = {"hostname": "Router.Example.COM"}

        result = normalize_device_hostname(device, self.job)
        self.assertEqual(result, "ROUTER")


class TestHasRequiredValues(TestCase):
    """Test required values validation."""

    def setUp(self):
        """Set up test case."""
        self.job = MagicMock()
        self.job.hostname_field = "hostname"

    def test_has_required_values_all_present(self):
        """Test when all required values are present."""
        device = {
            "hostname": "test-device",
            "location": "test-location",
            "type": "network",
            "os": "ios",
            "hardware": "cisco-ios",
            "load_errors": []
        }

        result = has_required_values(device, self.job)
        self.assertTrue(result)
        self.assertEqual(len(device["load_errors"]), 0)

    def test_has_required_values_missing_hostname(self):
        """Test when hostname is missing."""
        device = {
            "hostname": None,  # Missing hostname
            "location": "test-location",
            "type": "network",
            "os": "ios",
            "hardware": "cisco-ios",
            "load_errors": []
        }

        result = has_required_values(device, self.job)
        self.assertFalse(result)
        self.assertIn("hostname string is required", device["load_errors"])

    def test_has_required_values_empty_hostname(self):
        """Test when hostname is empty."""
        device = {
            "hostname": "",
            "location": "test-location",
            "type": "network",
            "os": "ios",
            "hardware": "cisco-ios",
            "load_errors": []
        }

        result = has_required_values(device, self.job)
        self.assertFalse(result)
        self.assertIn("hostname string is required", device["load_errors"])

    def test_has_required_values_multiple_missing(self):
        """Test when multiple required values are missing."""
        device = {
            "hostname": "test-device",
            "location": "",
            "type": None,
            "os": "ios",
            "hardware": "cisco-ios",
            "load_errors": []
        }

        result = has_required_values(device, self.job)
        self.assertFalse(result)
        self.assertIn("location string is required", device["load_errors"])
        self.assertIn("type string is required", device["load_errors"])


class TestHasValidLocationData(TransactionTestCase):
    """Test location data validation."""

    def setUp(self):
        """Set up test case."""
        self.job = MagicMock()
        self.job.location_type = LocationType.objects.create(name="SITE")
        
        # Create a status for the location
        from nautobot.extras.models import Status
        self.status, _created = Status.objects.get_or_create(name="Active")
        
        self.location, _created = Location.objects.get_or_create(
            name="Test Location",
            location_type=self.job.location_type,
            status=self.status
        )

    def test_has_valid_location_data_valid(self):
        """Test valid location data."""
        device = {"location": "Test Location", "load_errors": []}

        result = has_valid_location_data(device, "SITE")
        self.assertTrue(result)
        self.assertEqual(len(device["load_errors"]), 0)

    def test_has_valid_location_data_location_type_not_found(self):
        """Test when location type doesn't exist."""
        device = {"location": "Test Location", "load_errors": []}

        result = has_valid_location_data(device, "NonExistentType")
        self.assertFalse(result)
        self.assertTrue(len(device["load_errors"]) > 0)

    def test_has_valid_location_data_location_not_found(self):
        """Test when location doesn't exist."""
        device = {"location": "NonExistentLocation", "load_errors": []}

        result = has_valid_location_data(device, "SITE")
        self.assertFalse(result)
        self.assertTrue(len(device["load_errors"]) > 0)
        self.assertIn("Sync Locations from LibreNMS", device["load_errors"][0])


class TestHasValidRole(TransactionTestCase):
    """Test role validation."""

    def setUp(self):
        """Set up test case."""
        self.job = MagicMock()
        self.job.logger.info = MagicMock()

    def test_has_valid_role_existing_role(self):
        """Test when role already exists."""
        role = Role.objects.create(name="network")
        device = {"type": "network", "load_errors": []}

        result = has_valid_role(device, self.job)
        self.assertTrue(result)
        self.assertEqual(len(device["load_errors"]), 0)

    def test_has_valid_role_create_new_role(self):
        """Test creating a new role."""
        device = {"type": "new-role", "load_errors": []}

        result = has_valid_role(device, self.job)
        self.assertTrue(result)
        self.assertEqual(len(device["load_errors"]), 0)
        self.assertTrue(Role.objects.filter(name="new-role").exists())

    def test_has_valid_role_validation_error(self):
        """Test when role creation fails validation."""
        # Create a role with invalid name to trigger validation error
        device = {"type": "", "load_errors": []}

        result = has_valid_role(device, self.job)
        self.assertFalse(result)
        self.assertTrue(len(device["load_errors"]) > 0)


class TestHasValidManufacturerData(TransactionTestCase):
    """Test manufacturer data validation."""

    def setUp(self):
        """Set up test case."""
        self.job = MagicMock()
        self.job.logger.info = MagicMock()

    def test_has_valid_manufacturer_data_existing_manufacturer(self):
        """Test when manufacturer already exists."""
        manufacturer = Manufacturer.objects.create(name="Cisco")
        device = {"os": "ios", "load_errors": []}

        result = has_valid_manufacturer_data(device, self.job)
        self.assertTrue(result)
        self.assertEqual(len(device["load_errors"]), 0)

    def test_has_valid_manufacturer_data_create_new_manufacturer(self):
        """Test creating a new manufacturer."""
        device = {"os": "ios", "load_errors": []}

        result = has_valid_manufacturer_data(device, self.job)
        self.assertTrue(result)
        self.assertEqual(len(device["load_errors"]), 0)
        self.assertTrue(Manufacturer.objects.filter(name="Cisco").exists())

    def test_has_valid_manufacturer_data_unknown_os(self):
        """Test when OS is not in manufacturer map."""
        device = {"os": "unknown-os", "load_errors": []}

        result = has_valid_manufacturer_data(device, self.job)
        self.assertFalse(result)
        self.assertIn("Manufacturer is unknown", device["load_errors"])

    def test_has_valid_manufacturer_data_validation_error(self):
        """Test when manufacturer creation fails validation."""
        # Create a manufacturer with invalid name to trigger validation error
        device = {"os": "ios", "load_errors": []}
        
        # Mock the manufacturer creation to raise ValidationError
        with patch.object(Manufacturer.objects, 'create') as mock_create:
            mock_create.side_effect = ValidationError("Invalid manufacturer name")
            
            result = has_valid_manufacturer_data(device, self.job)
            self.assertFalse(result)
            self.assertTrue(len(device["load_errors"]) > 0)


class TestHasValidDeviceType(TransactionTestCase):
    """Test device type validation."""

    def setUp(self):
        """Set up test case."""
        self.job = MagicMock()
        self.job.logger.info = MagicMock()
        self.manufacturer = Manufacturer.objects.create(name="Cisco")

    def test_has_valid_device_type_existing(self):
        """Test when device type already exists."""
        device_type = DeviceType.objects.create(
            model="cisco-ios",
            manufacturer=self.manufacturer
        )
        device = {"hardware": "cisco-ios", "os": "ios", "load_errors": []}

        result = has_valid_device_type(device, self.job)
        self.assertTrue(result)
        self.assertEqual(len(device["load_errors"]), 0)

    def test_has_valid_device_type_create_new(self):
        """Test creating a new device type."""
        device = {"hardware": "new-model", "os": "ios", "load_errors": []}

        result = has_valid_device_type(device, self.job)
        self.assertTrue(result)
        self.assertEqual(len(device["load_errors"]), 0)
        self.assertTrue(DeviceType.objects.filter(model="new-model").exists())

    def test_has_valid_device_type_manufacturer_validation_fails(self):
        """Test when manufacturer validation fails."""
        device = {"hardware": "new-model", "os": "unknown-os", "load_errors": []}

        result = has_valid_device_type(device, self.job)
        self.assertFalse(result)
        self.assertTrue(len(device["load_errors"]) > 0)

    def test_has_valid_device_type_validation_error(self):
        """Test when device type creation fails validation."""
        device = {"hardware": "new-model", "os": "ios", "load_errors": []}
        
        # Mock the device type creation to raise ValidationError
        with patch.object(DeviceType.objects, 'create') as mock_create:
            mock_create.side_effect = ValidationError("Invalid device type")
            
            result = has_valid_device_type(device, self.job)
            self.assertFalse(result)
            self.assertTrue(len(device["load_errors"]) > 0)


class TestHasValidPlatform(TransactionTestCase):
    """Test platform validation."""

    def setUp(self):
        """Set up test case."""
        self.job = MagicMock()
        self.job.logger.info = MagicMock()

    def test_has_valid_platform_existing(self):
        """Test when platform already exists."""
        platform = Platform.objects.create(name="ios")
        device = {"os": "ios", "load_errors": []}

        result = has_valid_platform(device, self.job)
        self.assertTrue(result)
        self.assertEqual(len(device["load_errors"]), 0)

    def test_has_valid_platform_create_new(self):
        """Test creating a new platform."""
        device = {"os": "new-platform", "load_errors": []}

        result = has_valid_platform(device, self.job)
        self.assertTrue(result)
        self.assertEqual(len(device["load_errors"]), 0)
        self.assertTrue(Platform.objects.filter(name="new-platform").exists())

    def test_has_valid_platform_validation_error(self):
        """Test when platform creation fails validation."""
        device = {"os": "new-platform", "load_errors": []}
        
        # Mock the platform creation to raise ValidationError
        with patch.object(Platform.objects, 'create') as mock_create:
            mock_create.side_effect = ValidationError("Invalid platform")
            
            result = has_valid_platform(device, self.job)
            self.assertFalse(result)
            self.assertTrue(len(device["load_errors"]) > 0)


class TestValidateDeviceData(TransactionTestCase):
    """Test device data validation."""

    def setUp(self):
        """Set up test case."""
        self.job = MagicMock()
        self.job.hostname_field = "hostname"
        self.job.location_type = "Site"
        self.job.logger.info = MagicMock()
        
        # Create required objects
        self.location_type = LocationType.objects.create(name="Site")
        
        # Create a status for the location
        from nautobot.extras.models import Status
        self.status, _created = Status.objects.get_or_create(name="Active")
        
        self.location, _created = Location.objects.get_or_create(
            name="Test Location",
            location_type=self.location_type,
            status=self.status
        )
        self.role = Role.objects.create(name="network")
        self.manufacturer = Manufacturer.objects.create(name="Cisco")
        self.platform = Platform.objects.create(name="ios")

    @patch("nautobot_ssot.integrations.librenms.utils.settings")
    def test_validate_device_data_valid(self, mock_settings):
        """Test validating valid device data."""
        mock_settings.PLUGINS_CONFIG = {
            "nautobot_ssot": {
                "librenms_allow_ip_hostnames": True
            }
        }
        
        device = {
            "hostname": "192.168.1.1",
            "location": "Test Location",
            "type": "network",
            "os": "ios",
            "hardware": "cisco-ios",
            "load_errors": []
        }

        result = validate_device_data(device, self.job)
        
        self.assertIn("name", result)
        self.assertIn("location", result)
        self.assertIn("role", result)
        self.assertIn("manufacturer", result)
        self.assertIn("device_type", result)
        self.assertIn("platform", result)
        self.assertEqual(len(result["load_errors"]), 0)

    def test_validate_device_data_missing_required_values(self):
        """Test validating device data with missing required values."""
        device = {
            "hostname": "",
            "location": "Test Location",
            "type": "network",
            "os": "ios",
            "hardware": "cisco-ios",
            "load_errors": []
        }

        result = validate_device_data(device, self.job)
        
        self.assertEqual(len(result["load_errors"]), 1)
        self.assertIn("hostname string is required", result["load_errors"])

    def test_validate_device_data_duplicate_errors_removed(self):
        """Test that duplicate errors are removed."""
        device = {
            "hostname": "",
            "location": "",
            "type": "network",
            "os": "ios",
            "hardware": "cisco-ios",
            "load_errors": []
        }

        result = validate_device_data(device, self.job)
        
        # Should have unique errors only
        self.assertEqual(len(result["load_errors"]), 2)
        self.assertEqual(len(set(result["load_errors"])), 2)


class TestCheckSorField(TestCase):
    """Test System of Record field checking."""

    def setUp(self):
        """Set up test case."""
        self.model = MagicMock()
        self.model.custom_field_data = {}

    def test_check_sor_field_present_and_correct(self):
        """Test when SOR field is present and set to LibreNMS."""
        self.model.custom_field_data = {
            "system_of_record": "LibreNMS"
        }

        result = check_sor_field(self.model)
        self.assertTrue(result)

    def test_check_sor_field_present_but_wrong_value(self):
        """Test when SOR field is present but has wrong value."""
        self.model.custom_field_data = {
            "system_of_record": "OtherSystem"
        }

        result = check_sor_field(self.model)
        self.assertFalse(result)

    def test_check_sor_field_not_present(self):
        """Test when SOR field is not present."""
        result = check_sor_field(self.model)
        self.assertFalse(result)

    def test_check_sor_field_none_value(self):
        """Test when SOR field is None."""
        self.model.custom_field_data = {
            "system_of_record": None
        }

        result = check_sor_field(self.model)
        self.assertFalse(result)

    @patch.dict(os.environ, {"NAUTOBOT_SSOT_LIBRENMS_SYSTEM_OF_RECORD": "CustomSystem"})
    def test_check_sor_field_custom_system_of_record(self):
        """Test with custom system of record from environment."""
        self.model.custom_field_data = {
            "system_of_record": "CustomSystem"
        }

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
        self.nb_object.custom_field_data = {
            "system_of_record": "LibreNMS"
        }

        result = get_sor_field_nautobot_object(self.nb_object)
        self.assertEqual(result, "LibreNMS")

    def test_get_sor_field_nautobot_object_not_present(self):
        """Test when SOR field is not present."""
        result = get_sor_field_nautobot_object(self.nb_object)
        self.assertEqual(result, "")

    def test_get_sor_field_nautobot_object_none_value(self):
        """Test when SOR field is None."""
        self.nb_object.custom_field_data = {
            "system_of_record": None
        }

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
        mock_stack.return_value = [
            MagicMock(filename="/some/other/file.py"),
            MagicMock(filename="/another/file.py")
        ]

        result = is_running_tests()
        self.assertFalse(result)

    @patch("nautobot_ssot.integrations.librenms.utils.inspect.stack")
    def test_is_running_tests_with_unittest_in_stack(self, mock_stack):
        """Test when unittest/case.py is in the stack."""
        # Mock the stack to contain unittest/case.py
        mock_stack.return_value = [
            MagicMock(filename="/some/other/file.py"),
            MagicMock(filename="/path/to/unittest/case.py"),
            MagicMock(filename="/another/file.py")
        ]

        result = is_running_tests()
        self.assertTrue(result)
