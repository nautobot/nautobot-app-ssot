"""Tests for utility functions."""

import unittest
from importlib.metadata import PackageNotFoundError
from unittest.mock import MagicMock, patch

from django.apps import apps as django_apps
from nautobot.apps.testing import TestCase
from nautobot.dcim.models import Controller, ControllerManagedDeviceGroup, Location, LocationType
from nautobot.extras.choices import CustomFieldTypeChoices
from nautobot.extras.management import populate_status_choices
from nautobot.extras.models import Status

from nautobot_ssot.utils import (
    create_or_update_custom_field,
    get_username_password_https_from_secretsgroup,
    parse_hostname_for_location,
    parse_hostname_for_role,
    validate_dlm_installed,
    verify_controller_managed_device_group,
)


class TestSSoTUtils(unittest.TestCase):
    """Test SSoT utility functions."""

    def test_parse_hostname_for_role_success(self):
        """Validate the functionality of the parse_hostname_for_role method success."""
        hostname_mapping = [(".*EDGE.*", "Edge"), (".*DMZ.*", "DMZ")]
        hostname = "DMZ-switch.example.com"
        result = parse_hostname_for_role(
            hostname_map=hostname_mapping, device_hostname=hostname, default_role="Unknown"
        )
        self.assertEqual(result, "DMZ")

    def test_parse_hostname_for_role_failure(self):
        """Validate the functionality of the parse_hostname_for_role method failure."""
        hostname_mapping = []
        hostname = "core-router.example.com"
        result = parse_hostname_for_role(
            hostname_map=hostname_mapping, device_hostname=hostname, default_role="Unknown"
        )
        self.assertEqual(result, "Unknown")

    def test_validate_dlm_installed_successfully(self):
        """Validate the functionality of the validate_dlm_installed method works as expected."""
        with patch("nautobot_ssot.utils.version") as mock_version:
            mock_version.return_value = "2.0.0"
            result = validate_dlm_installed()
            self.assertTrue(result)

    def test_validate_dlm_installed_no_dlm(self):
        """Validate the functionality of the validate_dlm_installed method when DLM App isn't installed."""
        with patch("nautobot_ssot.utils.version") as mock_version:
            mock_version.side_effect = PackageNotFoundError
            result = validate_dlm_installed()
            self.assertFalse(result)

    def test_parse_hostname_for_location_no_map(self):
        """With no location_map, the device's own location is returned with no parent."""
        result = parse_hostname_for_location(location_map=None, device_hostname="sw01", device_location="HQ")
        self.assertEqual(result, {"name": "HQ", "parent": None})

    def test_parse_hostname_for_location_dict_match(self):
        """A dict location_map returns the matching pattern's Name/Parent."""
        location_map = {"^sw": {"Name": "Switchville", "Parent": "Region 1"}}
        result = parse_hostname_for_location(location_map=location_map, device_hostname="SW01", device_location="HQ")
        self.assertEqual(result, {"name": "Switchville", "parent": "Region 1"})

    def test_parse_hostname_for_location_dict_no_match(self):
        """A dict location_map with no matching pattern falls back to the device location."""
        location_map = {"^rtr": {"Name": "Routerville", "Parent": "Region 1"}}
        result = parse_hostname_for_location(location_map=location_map, device_hostname="sw01", device_location="HQ")
        self.assertEqual(result, {"name": "HQ", "parent": None})

    def test_parse_hostname_for_location_list_match(self):
        """A legacy list location_map returns the matching entry's location/parent."""
        location_map = [{"prefix": "^sw", "location": "Switchville", "parent": "Region 1"}]
        result = parse_hostname_for_location(location_map=location_map, device_hostname="sw01", device_location="HQ")
        self.assertEqual(result, {"name": "Switchville", "parent": "Region 1"})

    def test_parse_hostname_for_role_json_string(self):
        """A JSON-string hostname_map is decoded before matching."""
        result = parse_hostname_for_role(
            hostname_map='[["^sw", "Switch"]]', device_hostname="sw01", default_role="Unknown"
        )
        self.assertEqual(result, "Switch")

    def test_parse_hostname_for_role_invalid_json_string(self):
        """An invalid JSON-string hostname_map is treated as empty and returns the default role."""
        result = parse_hostname_for_role(hostname_map="not valid json{", device_hostname="sw01", default_role="Unknown")
        self.assertEqual(result, "Unknown")

    def test_get_username_password_https_from_secretsgroup(self):
        """The HTTPS username/password are read from the SecretsGroup and returned as a tuple."""
        group = MagicMock()
        group.get_secret_value.side_effect = ["my-user", "my-pass"]
        username, password = get_username_password_https_from_secretsgroup(group)
        self.assertEqual(username, "my-user")
        self.assertEqual(password, "my-pass")
        self.assertEqual(group.get_secret_value.call_count, 2)


class TestSSoTUtilsDatabase(TestCase):
    """Test SSoT utility functions that touch the database."""

    def test_create_or_update_custom_field(self):
        """create_or_update_custom_field creates the field, then updates it idempotently."""
        custom_field, created = create_or_update_custom_field(
            django_apps, key="ssot_test_cf", field_type=CustomFieldTypeChoices.TYPE_TEXT, label="SSoT Test CF"
        )
        self.assertTrue(created)
        self.assertEqual(custom_field.key, "ssot_test_cf")
        self.assertEqual(custom_field.label, "SSoT Test CF")

        # Second call with the same key updates rather than creates.
        _, created_again = create_or_update_custom_field(
            django_apps, key="ssot_test_cf", field_type=CustomFieldTypeChoices.TYPE_TEXT, label="SSoT Test CF Updated"
        )
        self.assertFalse(created_again)

    def test_verify_controller_managed_device_group(self):
        """verify_controller_managed_device_group returns (and creates) the Controller's device group."""
        populate_status_choices()
        status = Status.objects.get(name="Active")
        location_type = LocationType.objects.create(name="CtrlSite")
        location = Location.objects.create(name="Ctrl Location", location_type=location_type, status=status)
        controller = Controller.objects.create(name="Test Controller", status=status, location=location)

        group = verify_controller_managed_device_group(controller=controller)
        self.assertIsInstance(group, ControllerManagedDeviceGroup)
        self.assertEqual(group.controller, controller)
        self.assertEqual(group.name, "Test Controller Managed Devices")

        # Idempotent: calling again returns the same group.
        group_again = verify_controller_managed_device_group(controller=controller)
        self.assertEqual(group_again.pk, group.pk)
