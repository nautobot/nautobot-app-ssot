"""Tests for utility functions."""

import unittest

from nautobot_ssot.utils import parse_hostname_for_role


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
