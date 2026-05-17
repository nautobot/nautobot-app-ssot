"""Tests for utility functions."""

import unittest
from importlib.metadata import PackageNotFoundError
from unittest.mock import MagicMock, patch

from django.apps import apps
from django.test import TestCase
from nautobot.dcim.models import Controller, ControllerManagedDeviceGroup, Location, LocationType
from nautobot.extras.choices import SecretsGroupAccessTypeChoices, SecretsGroupSecretTypeChoices
from nautobot.extras.models import SecretsGroup, Status

from nautobot_ssot.exceptions import (
    AuthFailure,
    InvalidUrlScheme,
    JobException,
    MissingConfigSetting,
)
from nautobot_ssot.utils import (
    create_or_update_custom_field,
    get_username_password_https_from_secretsgroup,
    parse_hostname_for_location,
    parse_hostname_for_role,
    validate_dlm_installed,
    verify_controller_managed_device_group,
)


class TestSSoTUtils(unittest.TestCase):
    """Test SSoT utility functions that do not require database access."""

    def test_parse_hostname_for_role_success(self):
        """Hostname matching a configured regex returns the mapped role.

        Also exercises the JSON-string variant of `hostname_map` (the helper deserialises it
        before iterating), keeping both code paths verified in one place.
        """
        hostname_mapping = [(".*EDGE.*", "Edge"), (".*DMZ.*", "DMZ")]
        hostname = "DMZ-switch.example.com"
        self.assertEqual(
            parse_hostname_for_role(hostname_map=hostname_mapping, device_hostname=hostname, default_role="Unknown"),
            "DMZ",
        )
        self.assertEqual(
            parse_hostname_for_role(
                hostname_map='[[".*DMZ.*", "DMZ"]]', device_hostname=hostname, default_role="Unknown"
            ),
            "DMZ",
        )

    def test_parse_hostname_for_role_failure(self):
        """Hostname with no matching regex falls back to the supplied default role.

        Covers the empty-list, non-matching-list, and unparseable-JSON-string cases — all of
        which must return the supplied default without raising.
        """
        hostname = "core-router.example.com"
        for hostname_map in ([], [(".*EDGE.*", "Edge")], "{not-valid-json"):
            self.assertEqual(
                parse_hostname_for_role(hostname_map=hostname_map, device_hostname=hostname, default_role="Unknown"),
                "Unknown",
            )

    def test_validate_dlm_installed_successfully(self):
        """DLM is considered installed when importlib.metadata.version returns a version string."""
        with patch("nautobot_ssot.utils.version") as mock_version:
            mock_version.return_value = "2.0.0"
            result = validate_dlm_installed()
            self.assertTrue(result)

    def test_validate_dlm_installed_no_dlm(self):
        """DLM is considered absent when importlib.metadata.version raises PackageNotFoundError."""
        with patch("nautobot_ssot.utils.version") as mock_version:
            mock_version.side_effect = PackageNotFoundError
            result = validate_dlm_installed()
            self.assertFalse(result)


class TestParseHostnameForLocation(unittest.TestCase):
    """Test the dict, list and empty-map branches of parse_hostname_for_location."""

    def test_dict_map_matches_regex(self):
        """Dict-style map: a key whose regex matches the hostname returns its Name/Parent mapping."""
        location_map = {r"^nyc.*$": {"Name": "New York", "Parent": "US-East"}}
        result = parse_hostname_for_location(location_map, "nyc-edge-01", device_location="fallback")
        self.assertEqual(result, {"name": "New York", "parent": "US-East"})

    def test_list_map_matches_prefix(self):
        """Legacy list-style map.

        A matching prefix returns the entry's location/parent; a non-matching list falls through
        to the supplied device_location, exercising the post-loop fallback branch.
        """
        location_map = [{"prefix": "^lon", "location": "London", "parent": "EMEA"}]
        self.assertEqual(
            parse_hostname_for_location(location_map, "lon-core-01", device_location="fallback"),
            {"name": "London", "parent": "EMEA"},
        )
        self.assertEqual(
            parse_hostname_for_location(location_map, "par-core-01", device_location="fallback"),
            {"name": "fallback", "parent": None},
        )

    def test_empty_map_returns_device_location_fallback(self):
        """An empty/None map returns the supplied device_location as 'name' with no parent."""
        result = parse_hostname_for_location({}, "anything", device_location="DefaultSite")
        self.assertEqual(result, {"name": "DefaultSite", "parent": None})


class TestGetUsernamePasswordHttpsFromSecretsGroup(TestCase):
    """Test get_username_password_https_from_secretsgroup wires the right access/secret types."""

    def test_returns_username_then_password_tuple(self):
        """The helper invokes SecretsGroup.get_secret_value twice (HTTP/USERNAME then HTTP/PASSWORD) and returns the pair."""
        group = MagicMock(spec=SecretsGroup)
        group.get_secret_value.side_effect = ["user-x", "pass-x"]

        username, password = get_username_password_https_from_secretsgroup(group)

        self.assertEqual((username, password), ("user-x", "pass-x"))
        group.get_secret_value.assert_any_call(
            access_type=SecretsGroupAccessTypeChoices.TYPE_HTTP,
            secret_type=SecretsGroupSecretTypeChoices.TYPE_USERNAME,
        )
        group.get_secret_value.assert_any_call(
            access_type=SecretsGroupAccessTypeChoices.TYPE_HTTP,
            secret_type=SecretsGroupSecretTypeChoices.TYPE_PASSWORD,
        )


class TestVerifyControllerManagedDeviceGroup(TestCase):
    """Test verify_controller_managed_device_group is idempotent (creates once, reuses thereafter)."""

    def setUp(self):
        """Create the minimum DCIM scaffolding (status + location + controller) the helper requires."""
        status = Status.objects.get(name="Active")
        location_type = LocationType.objects.create(name="util-test-loc-type")
        location = Location.objects.create(name="util-test-loc", location_type=location_type, status=status)
        self.controller = Controller.objects.create(name="util-test-ctrl", status=status, location=location)

    def test_creates_then_reuses_managed_device_group(self):
        """First call creates the group with the default name; second call returns the same instance."""
        first = verify_controller_managed_device_group(self.controller)
        second = verify_controller_managed_device_group(self.controller)
        self.assertIsInstance(first, ControllerManagedDeviceGroup)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(first.name, f"{self.controller.name} Managed Devices")


class TestCreateOrUpdateCustomField(TestCase):
    """Test create_or_update_custom_field covers both the create and update branches."""

    def test_creates_then_updates_existing_field(self):
        """First call creates the CustomField; a second call with a new label updates the existing row."""
        cf, created = create_or_update_custom_field(apps, key="ssot_test_cf", field_type="text", label="Original")
        self.assertTrue(created)
        self.assertEqual(cf.label, "Original")

        cf2, created2 = create_or_update_custom_field(apps, key="ssot_test_cf", field_type="text", label="Updated")
        self.assertFalse(created2)
        self.assertEqual(cf.pk, cf2.pk)
        self.assertEqual(cf2.label, "Updated")


class TestSSoTExceptions(unittest.TestCase):
    """Test the four custom exception classes that override __init__ to populate attributes."""

    def test_auth_failure_carries_code_and_message(self):
        """AuthFailure exposes the supplied error_code as `expression` and message as `message`."""
        exc = AuthFailure(error_code="E401", message="bad credentials")
        self.assertEqual(exc.expression, "E401")
        self.assertEqual(exc.message, "bad credentials")
        self.assertEqual(str(exc), "bad credentials")

    def test_job_exception_carries_message(self):
        """JobException stores the supplied message as both `message` attr and stringified value."""
        exc = JobException(message="job failed to load")
        self.assertEqual(exc.message, "job failed to load")
        self.assertEqual(str(exc), "job failed to load")

    def test_invalid_url_scheme_formats_message(self):
        """InvalidUrlScheme builds its message from the offending scheme value."""
        exc = InvalidUrlScheme(scheme="ftp")
        self.assertEqual(exc.message, "Invalid URL scheme 'ftp' found!")
        self.assertEqual(str(exc), "Invalid URL scheme 'ftp' found!")

    def test_missing_config_setting_records_setting_name(self):
        """MissingConfigSetting captures the setting name and renders it into the message."""
        exc = MissingConfigSetting(setting="API_TOKEN")
        self.assertEqual(exc.setting, "API_TOKEN")
        self.assertEqual(exc.message, "Missing configuration setting - API_TOKEN!")
