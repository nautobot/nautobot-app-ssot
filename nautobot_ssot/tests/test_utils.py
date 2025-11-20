"""Tests for utility functions."""

import unittest
from importlib.metadata import PackageNotFoundError
from unittest.mock import patch

from nautobot_ssot.utils import (
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
