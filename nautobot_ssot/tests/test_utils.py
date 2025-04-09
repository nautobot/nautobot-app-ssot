"""Tests for utility functions."""

import unittest
from importlib.metadata import PackageNotFoundError
from unittest.mock import patch

from parameterized import parameterized

from nautobot_ssot.utils import (
    core_supports_softwareversion,
    dlm_supports_softwarelcm,
    parse_hostname_for_role,
    validate_dlm_installed,
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

    dlm_version = [
        ("dlm_v3.0.0", "3.0.0", False),
        ("dlm_v2.0.0", "2.0.0", True),
    ]

    @parameterized.expand(dlm_version, skip_on_empty=True)
    def test_dlm_supports_softwarelcm_successfully(self, name, sent, received):  # pylint: disable=unused-argument
        """Validate the functionality of the dlm_supports_softwarelcm method works as expected."""

        with patch("nautobot_ssot.utils.version") as mock_version:
            mock_version.return_value = sent
            result = dlm_supports_softwarelcm()
            self.assertEqual(result, received)

    def test_dlm_supports_softwarelcm_no_dlm(self):
        """Validate the functionality of the dlm_supports_softwarelcm method when DLM App isn't installed."""
        with patch("nautobot_ssot.utils.version") as mock_version:
            mock_version.side_effect = PackageNotFoundError
            result = dlm_supports_softwarelcm()
            self.assertFalse(result)

    core_nb_version = [
        ("core_v1.6.0", "1.6.0", False),
        ("core_v2.2.0", "2.2.0", True),
        ("core_v2.4.6", "2.4.6", True),
    ]

    @parameterized.expand(core_nb_version, skip_on_empty=True)
    def test_core_supports_softwareversion_successfully(self, name, sent, received):  # pylint: disable=unused-argument
        """Validate the functionality of the core_supports_softwareversion method works as expected."""
        with patch("nautobot_ssot.utils.version") as mock_version:
            mock_version.return_value = sent
            result = core_supports_softwareversion()
            self.assertEqual(result, received)

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
